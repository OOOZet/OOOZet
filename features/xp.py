# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023 Karol "digitcrusher" Łacina
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

import asyncio, discord, random
from datetime import datetime
from math import floor, sqrt

import console, database
from common import config, parse_duration

bot = None

def xp_to_level(xp):
  return floor(sqrt(xp / 50 + 0.25) - 0.5)

def level_to_xp(level):
  return level * (level + 1) // 2 * 100

async def update_roles_for(user):
  level = xp_to_level(database.data.get('xp', {}).get(user.id, 0))
  for threshold, role in config['xp_roles']:
    role = user.guild.get_role(role)
    if level >= threshold:
      await user.add_roles(role)
    else:
      await user.remove_roles(role)

async def update_roles():
  for user in bot.get_all_members():
    await update_roles_for(user)

def setup(_bot):
  global bot
  bot = _bot

  @bot.listen()
  async def on_message(msg):
    user = msg.author
    if user.bot or msg.channel.id in config['xp_ignored_channels'] or msg.channel.category_id in config['xp_ignored_categories']:
      return

    with database.lock:
      database.data.setdefault('xp_last_gain', {})
      if user.id in database.data['xp_last_gain']:
        now = datetime.now().astimezone()
        cooldown = parse_duration(config['xp_cooldown'])
        if (now - database.data['xp_last_gain'][user.id]).total_seconds() < cooldown:
          return
        database.data['xp_last_gain'][user.id] = now

    database.data.setdefault('xp', {}).setdefault(user.id, 0)
    old_level = xp_to_level(database.data['xp'][user.id])
    database.data['xp'][user.id] += random.randint(config['xp_min_gain'], config['xp_max_gain'])
    level = xp_to_level(database.data['xp'][user.id])
    database.should_save = True

    if level != old_level:
      await update_roles_for(user)
      if config['xp_channel'] is not None:
        announcement = random.choice([
          f'{user.mention} nie ma życia i dzięki temu jest już na poziomie {level}!',
          f'{user.mention} właśnie wszedł na wyższy poziom {level}!',
          f'{user.mention} zdobył kolejny poziom {level}. Brawo!',
          f'{user.mention} zdobył kolejny poziom {level}. Moje kondolencje.',
        ])
        await client.get_channel(config['xp_channel']).send(announcement)

  xp = discord.app_commands.Group(name='xp', description='Komendy do XP')
  bot.tree.add_command(xp)

  @bot.tree.context_menu(name='Pokaż XP')
  async def show(interaction, user: discord.User):
    xp = database.data.get('xp', {}).get(user.id, 0)
    level = xp_to_level(xp)
    left = level_to_xp(level + 1) - xp
    if user == interaction.user:
      await interaction.response.send_message(f'Masz {xp} XP i tym samym poziom {level}. Do następnego brakuje ci jeszcze {left} XP. 📈', ephemeral=True)
    else:
      await interaction.response.send_message(f'{user.mention} ma {xp} XP i tym samym poziom {level}. Do następnego brakuje mu jeszcze {left} XP. 📈', ephemeral=True)

  @xp.command(description='Wyświetla 10 użytkowników z najwyższym XP')
  async def leaderboard(interaction):
    ranking = sorted(database.data.get('xp', {}).items(), key=lambda x: x[1], reverse=True)[:10]
    result = f'Ranking 10 użytkowników z najwyższym XP: 🏆'
    for i, data in enumerate(ranking):
      user, xp = data
      level = xp_to_level(xp)
      result += f'\n{i + 1}. <@{user}> z {xp} XP i poziomem {level}'
    await interaction.response.send_message(result, ephemeral=True)

console.begin('xp')
console.register('update_roles', None, 'updates xp roles for all users', lambda: asyncio.run_coroutine_threadsafe(update_roles(), bot.loop).result())
console.end()
