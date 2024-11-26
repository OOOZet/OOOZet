# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023-2024 Karol "digitcrusher" Łacina
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

def get_xp(self):
  return database.data.get('xp', {}).get(self.id, 0)

def set_xp(self, value):
  database.data.setdefault('xp', {})[self.id] = value
  database.should_save = True

discord.User.xp = discord.Member.xp = property(fget=get_xp, fset=set_xp)

def xp_to_level(xp):
  return floor(sqrt(xp / 50 + 0.25) - 0.5)

def level_to_xp(level):
  return level * (level + 1) // 2 * 100

async def update_roles_for(member):
  logging.info(f'Updating XP roles for {member.id}')
  assert member.guild.id == config['guild']
  level = xp_to_level(member.xp)
  for threshold, role in config['xp_roles']:
    role = discord.Object(role)
    if level >= threshold:
      await member.add_roles(role)
    else:
      await member.remove_roles(role)

async def update_roles():
  logging.info('Updating XP roles for all members')
  for member in bot.get_guild(config['guild']).members:
    await update_roles_for(member)

async def setup(_bot):
  global bot
  bot = _bot

  lock = asyncio.Lock()

  @bot.listen()
  async def on_message(msg):
    member = msg.author
    if member.bot or msg.guild is None or msg.guild.id != config['guild'] or (msg.channel.id not in config['xp_unignored_channels'] and (msg.channel.id in config['xp_ignored_channels'] or msg.channel.category_id in config['xp_ignored_categories'])):
      return

    async with lock:
      now = datetime.now().astimezone()
      if member.id in database.data.setdefault('xp_last_gain', {}):
        cooldown = parse_duration(config['xp_cooldown'])
        if (now - database.data['xp_last_gain'][member.id]).total_seconds() < cooldown:
          return
      database.data['xp_last_gain'][member.id] = now

    gain = random.randint(config['xp_min_gain'], config['xp_max_gain'])
    logging.info(f'{member.id} gained {gain} XP')
    old_level = xp_to_level(member.xp)
    member.xp += gain
    level = xp_to_level(member.xp)

    if level != old_level:
      await update_roles_for(member)

      if config['xp_channel'] is not None:
        emoji = random.choice(['🥳', '🎉', '🎊'])
        announcement = random.choice([
          f'{member.mention} nie ma życia i dzięki temu jest już na poziomie **{level}**! {emoji}',
          f'{member.mention} właśnie wszedł na wyższy poziom **{level}**! {emoji}',
          f'{member.mention} zdobył kolejny poziom **{level}**. Brawo! {emoji}',
          f'{member.mention} zdobył kolejny poziom **{level}**. Moje kondolencje. {emoji}',
        ])
        await bot.get_channel(config['xp_channel']).send(announcement)

  xp = discord.app_commands.Group(name='xp', description='Komendy do XP')
  bot.tree.add_command(xp)

  async def show(interaction, user):
    level = xp_to_level(user.xp)
    left = level_to_xp(level + 1) - user.xp
    if user.bot:
      await interaction.response.send_message(f'{user.mention} jest botem i nie może zbierać XP… 😐', ephemeral=True)
    elif user == interaction.user:
      await interaction.response.send_message(f'Masz **{user.xp} XP** i tym samym **poziom {level}**. Do następnego brakuje ci jeszcze **{left} XP**. 📈', ephemeral=True)
    else:
      await interaction.response.send_message(f'{user.mention} ma **{user.xp} XP** i tym samym **poziom {level}**. Do następnego brakuje mu/jej jeszcze **{left} XP**. 📈', ephemeral=True)

  @xp.command(name='show', description='Pokazuje XP użytkownika')
  async def cmd_show(interaction, user: discord.User | None):
    await show(interaction, interaction.user if user is None else user)

  @bot.tree.context_menu(name='Pokaż XP')
  async def menu_show(interaction, user: discord.User):
    await show(interaction, user)

  @xp.command(description='Wyświetla 10 użytkowników z najwyższym XP')
  async def leaderboard(interaction):
    if not database.data.get('xp', {}):
      await interaction.response.send_message('Nikt jeszcze nie zebrał żadnego XP. 😴', ephemeral=True)
      return

    result = f'Ranking 10 użytkowników z najwyższym XP: 🏆\n'
    ranking = sorted(database.data['xp'].items(), key=lambda x: x[1], reverse=True)[:10]
    for i, entry in enumerate(ranking):
      user, xp = entry
      result += f'{i + 1}. <@{user}> z **{xp} XP** i poziomem **{xp_to_level(xp)}**\n'
    await interaction.response.send_message(result, ephemeral=True)

  @xp.command(description='Wyświetla role za XP')
  async def roles(interaction):
    if not config['xp_roles']:
      await interaction.response.send_message('Niestety nie ma żadnych ról, które mógłbyś dostać za XP. 😭', ephemeral=True)
      return

    result = 'Za zdobywanie kolejnych poziomów możesz dostać następujące role: 💰\n'
    for level, role in config['xp_roles']:
      result += f'- <@&{role}> za poziom **{level}**\n'
    await interaction.response.send_message(result, ephemeral=True)

console.begin('xp')
console.register('update_roles', None, 'updates XP roles for all members', lambda: asyncio.run_coroutine_threadsafe(update_roles(), bot.loop).result())
console.end()
