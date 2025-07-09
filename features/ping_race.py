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

import asyncio, discord
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import console, database
from common import config, hybrid_check, pages_view

bot = None
lock = asyncio.Lock()

class NoPingRaceRoleError(discord.app_commands.CheckFailure):
  pass

@hybrid_check(is_consistent=True)
def check_ping_race_role(interaction):
  if config['ping_race_role'] is None:
    raise NoPingRaceRoleError()

async def check(msg):
  if all(i.id != config['ping_race_role'] for i in msg.role_mentions):
    return
  time = msg.created_at.astimezone(ZoneInfo(config['timezone']))
  if time.hour != config['ping_race_hour'] or time.minute != config['ping_race_minute']:
    return
  date = time.date().isoformat()
  async with lock:
    if date not in database.data.setdefault('ping_race_days', {}) or time < database.data['ping_race_days'][date]['time']:
      database.data['ping_race_days'][date] = {
        'winner': msg.author.id,
        'time': time,
        'msg': msg.id,
        'channel': msg.channel.id,
      }

async def check_all():
  guild = bot.get_guild(config['guild'])
  after = datetime.now().astimezone() - timedelta(days=config['ping_race_max_age_days'] + 1)
  for channel in guild.channels:
    if hasattr(channel, 'history'):
      try:
        async for msg in channel.history(after=after, limit=None):
          await check(msg)
      except discord.errors.Forbidden:
        pass
  for thread in guild.threads:
    async for msg in thread.history(after=after, limit=None):
      await check(msg)

async def setup(_bot):
  global bot
  bot = _bot

  @bot.on_check_failure
  async def on_check_failure(interaction, error):
    if isinstance(error, NoPingRaceRoleError):
      await interaction.response.send_message('Na tym serwerze nie została jeszcze stworzona rola do wspólnego pingowania. 😔', ephemeral=True)
    else:
      raise

  @bot.listen()
  async def on_message(msg):
    await check(msg)

  @bot.tree.command(name='ping-race', description='Wyświetla najszybszych pingujących w ostatnim czasie')
  @check_ping_race_role
  async def ping_race(interaction):
    ranking = {}
    today = datetime.now(ZoneInfo(config['timezone'])).date()
    date = today - timedelta(days=config['ping_race_max_age_days'])
    while date <= today:
      user = database.data.get('ping_race_days', {}).get(date.isoformat(), {}).get('winner')
      if user is not None:
        ranking.setdefault(user, 0)
        ranking[user] += 1
      date += timedelta(days=1)
    ranking = sorted(ranking.items(), key=lambda x: x[1], reverse=True)

    if not ranking:
      await interaction.response.send_message(f'Nikt jeszcze nie spingował <@&{config["ping_race_role"]}> o {config["ping_race_hour"]}:{config["ping_race_minute"]} w ostatnim czasie. 😔', ephemeral=True)
      return

    def contents_of(page):
      result = f'Ranking użytkowników według liczby najszybszych pingów <@&{config["ping_race_role"]}> w ostatnim czasie: 🏃\n'
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

console.begin('ping_race')
console.register('check_all', None, 'checks all relevant messages', lambda: asyncio.run_coroutine_threadsafe(check_all(), bot.loop).result())
console.end()
