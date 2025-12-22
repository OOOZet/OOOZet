# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023-2025 Karol "digitcrusher" Łacina
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

import asyncio, datetime as dt, discord, logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import console, database
from common import config, hybrid_check, pages_view

bot = None
lock = asyncio.Lock()

class NoBudzikRolesError(discord.app_commands.CheckFailure):
  pass

@hybrid_check(is_consistent=True)
def check_budzik_roles(interaction):
  if not config['budzik_roles']:
    raise NoBudzikRolesError()

async def check(msg):
  if msg.channel.id != config['budzik_channel'] or not config['budzik_roles'] or all(i.id != config['budzik_roles'][0][0] for i in msg.role_mentions):
    return
  time = msg.created_at.astimezone(ZoneInfo(config['timezone']))
  logging.info(f'User {msg.author.id} pinged role {config["budzik_roles"][0][0]} at {time}')
  date = time.date().isoformat()
  async with lock:
    if time <= database.data.setdefault('budzik_first_pings', {}).setdefault(date, {}).get(msg.author.id, time):
      database.data['budzik_first_pings'][date][msg.author.id] = time
      database.should_save = True

async def check_all():
  logging.info('Checking all relevant #budzik messages')
  after = datetime.now().astimezone() - timedelta(days=config['budzik_max_age_days'] + 1)
  async for msg in bot.get_channel(config['budzik_channel']).history(after=after, limit=None):
    await check(msg)

async def setup(_bot):
  global bot
  bot = _bot

  @bot.on_check_failure
  async def on_check_failure(interaction, error):
    if isinstance(error, NoBudzikRolesError):
      await interaction.response.send_message('Na tym serwerze nie została jeszcze stworzona żadna rola do wspólnego pingowania. 😔', ephemeral=True)
    else:
      raise

  @bot.listen()
  async def on_message(msg):
    await check(msg)

  @bot.tree.command(name='budzik', description='Wyświetla najszybszych pingujących w ostatnim czasie')
  @check_budzik_roles
  async def budzik(interaction):
    role, hour, minute = config['budzik_roles'][0]

    ranking = {}
    today = datetime.now(ZoneInfo(config['timezone'])).date()
    date = today - timedelta(days=config['budzik_max_age_days'])
    while date <= today:
      first_pings = filter(lambda x: x[1].hour == hour and x[1].minute == minute, database.data.get('budzik_first_pings', {}).get(date.isoformat(), {}).items())
      try:
        user = min(first_pings, key=lambda x: x[1])[0]
      except ValueError:
        pass
      else:
        ranking.setdefault(user, 0)
        ranking[user] += 1
      date += timedelta(days=1)
    ranking = sorted(ranking.items(), key=lambda x: x[1], reverse=True)

    if not ranking:
      await interaction.response.send_message(f'Nikt jeszcze nie spingował <@&{role}> o {hour}:{minute:02} w ostatnim czasie. 😔', ephemeral=True)
      return

    def contents_of(page):
      result = f'Ranking użytkowników według liczby najszybszych pingów <@&{role}> w ostatnim czasie: 🏃\n'
      for i in range(20 * page, 20 * (page + 1)):
        try:
          user, score = ranking[i]
        except IndexError:
          break
        result += f'{i + 1}. <@{user}> z **{score}** ' + ('najszybszym pingiem\n' if score == 1 else 'najszybszymi pingami\n')
      return result

    async def on_select_page(interaction2, page):
      await interaction2.response.defer()
      await interaction2.edit_original_response(content=contents_of(page), view=view)
    view = pages_view(0, (len(ranking) + 20 - 1) // 20, on_select_page, interaction.user)

    await interaction.response.send_message(contents_of(0), view=view, ephemeral=True)

  def create_tasks(role, hour, minute):
    lock = asyncio.Lock()
    should_be_mentionable = None

    logging.info(f'Scheduling the setting of role {role} to be mentionable for {hour}:{minute - 1:02}')
    @discord.ext.tasks.loop(time=dt.time(hour, minute - 1, tzinfo=ZoneInfo(config['timezone'])))
    async def enable():
      async with lock:
        if not enable.failed():
          nonlocal should_be_mentionable
          should_be_mentionable = True
        if not should_be_mentionable:
          logging.warn(f'Giving up on setting role {role} to be mentionable')
          return
        logging.info(f'Setting role {role} to be mentionable')
        await bot.get_guild(config['guild']).get_role(role).edit(mentionable=True)
    enable.start()

    logging.info(f'Scheduling the setting of role {role} to not be mentionable for {hour}:{minute + 1:02}')
    @discord.ext.tasks.loop(time=dt.time(hour, minute + 1, tzinfo=ZoneInfo(config['timezone'])))
    async def disable():
      async with lock:
        if not disable.failed():
          nonlocal should_be_mentionable
          should_be_mentionable = False
        if should_be_mentionable:
          logging.warn(f'Giving up on setting role {role} to not be mentionable')
          return
        logging.info(f'Setting role {role} to not be mentionable')
        await bot.get_guild(config['guild']).get_role(role).edit(mentionable=False)
    disable.start()

  for role, hour, minute in config['budzik_roles']:
    create_tasks(role, hour, minute)

console.begin('budzik')
console.register('check_all', None, 'checks all relevant messages', lambda: asyncio.run_coroutine_threadsafe(check_all(), bot.loop).result())
console.end()
