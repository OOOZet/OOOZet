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

import asyncio, discord, logging, random
from datetime import datetime
from math import floor, sqrt

import console, database
from common import config, parse_duration

bot = None

def xp_to_level(xp):
  return floor(sqrt(xp / 50 + 0.25) - 0.5)

def level_to_xp(level):
  return level * (level + 1) // 2 * 100

async def update_roles_for(member):
  logging.info(f'Updating XP roles for {member.id}')
  level = xp_to_level(database.data.get('xp', {}).get(member.id, 0))
  for threshold, role in config['xp_roles']:
    role = member.guild.get_role(role)
    if level >= threshold:
      await member.add_roles(role)
    else:
      await member.remove_roles(role)

async def update_roles():
  logging.info('Updating XP roles for all members')
  for member in bot.get_all_members():
    await update_roles_for(member)

def setup(_bot):
  global bot
  bot = _bot

  @bot.listen()
  async def on_message(msg):
    member = msg.author
    if member.bot or msg.channel.id in config['xp_ignored_channels'] or msg.channel.category_id in config['xp_ignored_categories']:
      return

    with database.lock:
      now = datetime.now().astimezone()
      if member.id in database.data.setdefault('xp_last_gain', {}):
        cooldown = parse_duration(config['xp_cooldown'])
        if (now - database.data['xp_last_gain'][member.id]).total_seconds() < cooldown:
          return
      database.data['xp_last_gain'][member.id] = now

    gain = random.randint(config['xp_min_gain'], config['xp_max_gain'])
    logging.info(f'{member.id} gained {gain} XP')
    old_level = xp_to_level(database.data.setdefault('xp', {}).setdefault(member.id, 0))
    database.data['xp'][member.id] += gain
    database.should_save = True
    level = xp_to_level(database.data['xp'][member.id])

    if level != old_level:
      await update_roles_for(member)

      if config['xp_channel'] is not None:
        announcement = random.choice([
          f'{member.mention} nie ma życia i dzięki temu jest już na poziomie {level}! 🥳',
          f'{member.mention} właśnie wszedł na wyższy poziom {level}! 🥳',
          f'{member.mention} zdobył kolejny poziom {level}. Brawo! 🥳',
          f'{member.mention} zdobył kolejny poziom {level}. Moje kondolencje. 🥳',
        ])
        await bot.get_channel(config['xp_channel']).send(announcement)

  xp = discord.app_commands.Group(name='xp', description='Komendy do XP')
  bot.tree.add_command(xp)

  async def show(interaction, user):
    xp = database.data.get('xp', {}).get(user.id, 0)
    level = xp_to_level(xp)
    left = level_to_xp(level + 1) - xp
    if user.bot:
      await interaction.response.send_message(f'{user.mention} jest botem i nie może zbierać XP… 😐', ephemeral=True)
    elif user == interaction.user:
      await interaction.response.send_message(f'Masz {xp} XP i tym samym poziom {level}. Do następnego brakuje ci jeszcze {left} XP. 📈', ephemeral=True)
    else:
      await interaction.response.send_message(f'{user.mention} ma {xp} XP i tym samym poziom {level}. Do następnego brakuje mu jeszcze {left} XP. 📈', ephemeral=True)

  @xp.command(name='show', description='Pokazuje XP użytkownika')
  async def cmd_show(interaction, user: discord.User | None):
    await show(interaction, interaction.user if user is None else user)

  @bot.tree.context_menu(name='Pokaż XP')
  async def menu_show(interaction, user: discord.User):
    await show(interaction, user)

  @xp.command(description='Wyświetla 10 użytkowników z najwyższym XP')
  async def leaderboard(interaction):
    ranking = sorted(database.data.get('xp', {}).items(), key=lambda x: x[1], reverse=True)[:10]
    result = f'Ranking 10 użytkowników z najwyższym XP: 🏆\n'
    for i, entry in enumerate(ranking):
      user, xp = entry
      level = xp_to_level(xp)
      result += f'{i + 1}. <@{user}> z {xp} XP i poziomem {level}\n'
    await interaction.response.send_message(result, ephemeral=True)

  @xp.command(description='Wyświetla role za XP')
  async def roles(interaction):
    if not config['xp_roles']:
      await interaction.response.send_message('Niestety nie ma żadnych ról, które mógłbyś dostać za XP. 😭', ephemeral=True)
      return

    result = 'Za zdobywanie kolejnych poziomów możesz dostać następujące role: 💰\n'
    for level, role in config['xp_roles']:
      result += f'- <@&{role}> za poziom {level}\n'
    await interaction.response.send_message(result, ephemeral=True)

console.begin('xp')
console.register('update_roles', None, 'updates XP roles for all members', lambda: asyncio.run_coroutine_threadsafe(update_roles(), bot.loop).result())
console.end()
