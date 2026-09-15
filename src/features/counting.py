# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023-2026 Karol "digitcrusher" Łacina
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import asyncio
from datetime import datetime
from discord import app_commands

import console, database
from common import config, event_listener, hybrid_check, pages_view

lock = asyncio.Lock()

class NoCountingChannelError(app_commands.CheckFailure):
  pass

@hybrid_check(is_consistent=True)
def check_counting_channel(interaction):
  if config['counting_channel'] is None:
    raise NoCountingChannelError()

@event_listener
async def on_check_failure(interaction, error):
  if isinstance(error, NoCountingChannelError):
    await interaction.response.send_message('Na tym serwerze nie został jeszcze stworzony kanał #liczenie. 😴', ephemeral=True)
  else:
    raise

bad_messages = set()

async def clean():
  if config['counting_channel'] is None:
    return

  if 'counting_clean_until' not in database.data:
    log.info('#counting has never been cleaned before')
    database.data['counting_clean_until'] = datetime.now().astimezone()
    database.should_save = True

  async with lock:
    async for msg in bot.get_channel(config['counting_channel']).history(limit=None, after=database.data['counting_clean_until']):
      try:
        num = int(msg.content, 0)
      except ValueError:
        bad_messages.add(msg.id)
        await msg.delete()
      else:
        if num == database.data.get('counting_num', num) and not msg.author.bot:
          if 'counting_num' in database.data:
            log.info(f'{msg.author.id} has upped the counting number to {num}')
          else:
            log.info(f'{msg.author.id} has called the initial counting number at {num}')

          database.data['counting_num'] = num + 1
          database.data['counting_clean_until'] = msg.created_at
          database.data['counting_score'][msg.author.id] = database.data.setdefault('counting_score', {}).get(msg.author.id, 0) + 1
          database.should_save = True
        else:
          bad_messages.add(msg.id)
          await msg.delete()

@event_listener
async def on_ready():
  log.info('Cleaning #counting')
  await clean()
  log.info('Counting is ready')

@event_listener
async def on_message(msg):
  if msg.channel.id == config['counting_channel']:
    log.info('Cleaning #counting after a new message')
    await clean() # on_message can come before on_ready.

@app_commands.command(description='Wyświetla ranking kanału #liczenie')
@check_counting_channel
async def counting(interaction):
  ranking = sorted(database.data.get('counting_score', {}).items(), key=lambda x: x[1], reverse=True)
  if not ranking:
    await interaction.response.send_message(f'Nikt jeszcze nie skorzystał z <#{config["counting_channel"]}>. 😴', ephemeral=True)
    return

  def contents_of(page):
    result = f'Ranking najbardziej aktywnych użytkowników <#{config["counting_channel"]}>: 🔢\n'
    for i in range(20 * page, 20 * (page + 1)):
      try:
        user, score = ranking[i]
      except IndexError:
        break
      result += f'{i + 1}. <@{user}> z **{score}** ' + ('wysłaną wiadomością\n' if score == 1 else 'wysłanymi wiadomościami\n')
    return result

  async def refresh(interaction2, page):
    await interaction2.response.defer()
    await interaction2.edit_original_response(content=contents_of(page), view=view)
  view = pages_view(0, (len(ranking) + 20 - 1) // 20, refresh, interaction.user)

  await interaction.response.send_message(contents_of(0), view=view, ephemeral=True)

@event_listener
async def on_message_delete(msg):
  if msg.channel.id == config['counting_channel']:
    async with lock:
      if msg.id not in bad_messages: # We have no other way of checking if we caused this event.
        log.info(f'{msg.author.id} deleted their message in #counting')
        database.data['counting_score'][msg.author.id] -= 1
        database.should_save = True

@console.operation(desc='recalculates the counting ranking')
async def recalc():
  log.info('Recalculating the counting ranking')
  async with lock:
    database.data['counting_score'] = {}
    async for msg in bot.get_channel(config['counting_channel']).history(limit=None):
      database.data['counting_score'][msg.author.id] = database.data['counting_score'].get(msg.author.id, 0) + 1
    database.should_save = True
