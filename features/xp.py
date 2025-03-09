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

import asyncio, discord, logging, random
from datetime import datetime
from math import floor, sqrt
from threading import Lock

import console, database
from common import config, hybrid_check, pages_view, parse_duration

bot = None
lock = Lock()

def get_xp(self):
  return database.data.get('xp', {}).get(self.id, 0)

def set_xp(self, value):
  database.data.setdefault('xp', {})[self.id] = value
  database.should_save = True

discord.User.xp = discord.Member.xp = property(get_xp, set_xp)

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

class NoXpRolesError(discord.app_commands.CheckFailure):
  pass

@hybrid_check(is_consistent=True)
def check_xp_roles(interaction):
  if not config['xp_roles']:
    raise NoXpRolesError()

async def setup(_bot):
  global bot
  bot = _bot

  @bot.on_check_failure
  async def on_check_failure(interaction, error):
    if isinstance(error, NoXpRolesError):
      await interaction.response.send_message('Niestety nie ma żadnych ról, które mógłbyś dostać za XP. 😭', ephemeral=True)
    else:
      raise

  @bot.listen()
  async def on_message(msg):
    member = msg.author
    if member.bot or msg.guild is None or msg.guild.id != config['guild'] or (msg.channel.id not in config['xp_unignored_channels'] and (msg.channel.id in config['xp_ignored_channels'] or msg.channel.category_id in config['xp_ignored_categories'])):
      return

    with lock:
      now = datetime.now().astimezone()
      if member.id in database.data.setdefault('xp_last_gain', {}):
        cooldown = parse_duration(config['xp_cooldown'])
        if (now - database.data['xp_last_gain'][member.id]).total_seconds() < cooldown:
          return
      database.data['xp_last_gain'][member.id] = now

    gain = random.randint(config['xp_min_gain'], config['xp_max_gain'])
    logging.info(f'{member.id} gained {gain} XP')
    with lock:
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
        await bot.get_channel(config['xp_channel']).send(announcement, allowed_mentions=discord.AllowedMentions.all())

  xp = discord.app_commands.Group(name='xp', description='Komendy do XP')
  bot.tree.add_command(xp)

  async def show(interaction, marked_user):
    if marked_user.bot:
      await interaction.response.send_message(f'{marked_user.mention} jest botem i nie może zbierać XP… 😐', ephemeral=True)
      return

    ranking = sorted(database.data['xp'].items(), key=lambda x: x[1], reverse=True)
    def contents_of(page):
      result = 'Ranking użytkowników według XP: 🏆\n'
      for i in range(20 * page, 20 * (page + 1)):
        try:
          user, xp = ranking[i]
        except IndexError:
          break
        level = xp_to_level(xp)
        left = level_to_xp(level + 1) - xp
        result += f'{i + 1}. <@{user}> z **{xp} XP** i poziomem **{level}** - do następnego **{left} XP**' + (' **⬅️**\n' if user == marked_user.id else '\n')
      return result

    try:
      init_page = next(i for i, entry in enumerate(ranking) if entry[0] == marked_user.id) // 20
    except StopIteration:
      await interaction.response.send_message(f'{marked_user.mention} nie zebrał jeszcze żadnego XP. 😴', ephemeral=True)
      return
    async def on_select_page(interaction2, page):
      await interaction2.response.defer()
      await interaction2.edit_original_response(content=contents_of(page), view=view)
    view = pages_view(init_page, (len(ranking) + 20 - 1) // 20, on_select_page, interaction.user)

    await interaction.response.send_message(contents_of(init_page), view=view, ephemeral=True)

  @xp.command(name='show', description='Pokazuje ranking XP z zaznaczonym użytkownikiem')
  async def cmd_show(interaction, user: discord.User | None):
    await show(interaction, interaction.user if user is None else user)

  @bot.tree.context_menu(name='Pokaż XP')
  async def menu_show(interaction, user: discord.User):
    await show(interaction, user)

  @xp.command(description='Wyświetla role za XP')
  @check_xp_roles
  async def roles(interaction):
    result = 'Za zdobywanie kolejnych poziomów możesz dostać następujące role: 💰\n'
    for level, role in config['xp_roles']:
      result += f'- <@&{role}> za poziom **{level}**\n'
    await interaction.response.send_message(result, ephemeral=True)

async def transfer(from_, to):
  with lock:
    database.data['xp'][to] += database.data['xp'][from_]
    database.data['xp'][from_] = 0
    database.should_save = True

  if (member := bot.get_guild(config['guild']).get_member(from_)) is not None:
    await update_roles_for(member)
  if (member := bot.get_guild(config['guild']).get_member(to)) is not None:
    await update_roles_for(member)

def init(user):
  with lock:
    database.data.setdefault('xp', {}).setdefault(user, 0)
    database.should_save = True

console.begin('xp')
console.register('update_roles', None, 'updates XP roles for all members', lambda: asyncio.run_coroutine_threadsafe(update_roles(), bot.loop).result())
console.register('transfer', '<from> <to>', 'transfers XP from one account to another', lambda x: asyncio.run_coroutine_threadsafe(transfer(*map(int, x.split())), bot.loop).result())
console.register('init', '<id>', 'makes sure the XP database entry for a user exists', lambda x: init(int(x)))
console.end()
