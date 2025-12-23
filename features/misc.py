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

import discord, logging, random
from datetime import datetime

import database
from common import config, debacktick, hybrid_check, parse_duration
from features import warns, xp
from features.utils import check_staff

bot = None

def get_staff():
  return {i for role in config['staff_roles'] for i in bot.get_guild(config['guild']).get_role(role).members}

class NoStaffError(discord.app_commands.CheckFailure):
  pass

@hybrid_check()
def check_staff_nonempty(interaction):
  if all(not bot.get_guild(config['guild']).get_role(i).members for i in config['staff_roles']):
    raise NoStaffError()

async def setup(_bot):
  global bot
  bot = _bot

  @bot.on_check_failure
  async def on_check_failure(interaction, error):
    if isinstance(error, NoStaffError):
      await interaction.response.send_message('Hmm, z jakiegoś powodu nie jest mi znane, żeby ktoś był w administracji… 🧐', ephemeral=True)
    else:
      raise

  @bot.tree.command(name='fix-roles', description='Naprawia role użytkownika')
  @discord.app_commands.guilds(config['guild'])
  async def fix_roles(interaction, member: discord.Member | None):
    if member is None:
      member = interaction.user
    logging.info(f'Received user request to update roles for {member.id}')
    await interaction.response.defer(ephemeral=True)
    await warns.update_roles_for(member)
    await xp.update_roles_for(member)
    await interaction.followup.send(f'Pomyślnie zaktualizowano role za warny i XP dla {member.mention}. 👌')

  @bot.listen()
  async def on_member_join(member):
    if member.guild.id != config['guild']:
      return

    logging.info(f'{member.id} joined the guild')
    await warns.update_roles_for(member)
    await xp.update_roles_for(member)
    if member.is_timed_out() and config['timeout_role'] is not None:
      await member.add_roles(discord.Object(config['timeout_role']))

  @bot.listen()
  async def on_member_remove(member):
    if member.guild.id != config['guild']:
      return

    logging.info(f'{member.id} left the guild')
    if member.guild.system_channel_flags.join_notifications:
      announcement = random.choice([
        f'Niestety nie ma już `{member.our_name}` z nami… 🕯️',
        f'Chwila ciszy dla `{member.our_name}`… 🕯️',
        f'`{member.our_name}` już nie mógł wytrzymać tego syfu i wyszedł… 🕯️',
        f'`{member.our_name}` wyszedł z serwera… 🕯️',
      ])
      await member.guild.system_channel.send(announcement)

  @bot.tree.command(description='Wzywa administrację po pomoc')
  @discord.app_commands.guilds(config['guild'])
  @check_staff_nonempty
  async def alarm(interaction):
    now = datetime.now().astimezone()

    if 'alarm_last' in database.data:
      cooldown = parse_duration(config['alarm_cooldown'])
      if (now - database.data['alarm_last']).total_seconds() < cooldown:
        await interaction.response.send_message(f'Alarm już zabrzmiał w ciągu ostatnich **{cooldown}** sekund. ⏱️', ephemeral=True)
        return

    logging.info(f'{interaction.user.id} has raised the alarm!')
    database.data['alarm_last'] = now
    database.should_save = True

    staff = get_staff()
    emoji = random.choice(['😟', '😖', '😱', '😮', '😵', '😵‍💫', '🥴'])
    mentions = ' '.join(i.mention for i in staff)
    await interaction.response.send_message(f'{mentions} Potrzebna natychmiastowa interwencja!!! {emoji}', allowed_mentions=discord.AllowedMentions.all())
    for user in staff:
      msg = (await interaction.original_response()).jump_url
      await user.send(f'{interaction.user.mention} potrzebuje natychmiastowej interwencji na {msg}!!! {emoji}')
      await user.send('https://c.tenor.com/EDeg5ifIrjQAAAAC/alarm-better-discord.gif')

  @bot.tree.command(description='Wyświetla skład administracji')
  @check_staff_nonempty
  async def staff(interaction):
    result = ''.join(f'- {i.mention}\n' for i in get_staff())
    await interaction.response.send_message(f'W administracji serwera znajdują się: 👮\n{result}', ephemeral=True)

  @bot.listen()
  async def on_member_update(before, after):
    if before.is_timed_out() != after.is_timed_out() and config['timeout_role'] is not None:
      role = discord.Object(config['timeout_role'])
      if after.is_timed_out():
        logging.info(f'{after.id} has been timed out')
        await after.add_roles(role)
      else:
        logging.info(f"{after.id}'s timeout has been manually removed")
        await after.remove_roles(role)

  @discord.ext.tasks.loop(seconds=parse_duration(config['timeout_poll_rate']))
  async def poll_timeouts():
    if config['timeout_role'] is not None:
      await bot.wait_until_ready()
      for member in bot.get_guild(config['guild']).get_role(config['timeout_role']).members:
        if not member.is_timed_out():
          logging.info(f"{member.id}'s timeout has expired")
          await member.remove_roles(discord.Object(config['timeout_role']))

  poll_timeouts.start()

  @bot.listen()
  async def on_message(msg):
    if msg.channel.id in config['media_channels'] and all(i.width is None and i.height is None for i in msg.attachments):
      await msg.delete()

  async def kick(interaction, member):
    if not isinstance(member, discord.Member):
      await interaction.response.send_message(f'{member.mention} nie jest już na tym serwerze… 🤨', ephemeral=True)
    elif interaction.user == member:
      await interaction.response.send_message('Nie możesz skickować samego siebie… 🤨', ephemeral=True)
    elif interaction.user.top_role <= member.top_role and interaction.user != interaction.guild.owner:
      await interaction.response.send_message(f'Nie jesteś wyżej w hierarchii od {member.mention}… 🤨', ephemeral=True)
    else:
      try:
        await member.kick(reason=f'Na żądanie {interaction.user.our_name}')
      except discord.Forbidden:
        await interaction.response.send_message(f'Nie mam uprawnień, żeby skickować {member.mention}… 🧐', ephemeral=True)
      else:
        logging.info(f'{interaction.user.id} kicked {member.id}')
        await interaction.response.send_message(f'Pomyślnie skickowano {member.mention}. 😒', ephemeral=True, allowed_mentions=discord.AllowedMentions.all())

  @bot.tree.command(name='kick', description='Kickuje użytkownika')
  @discord.app_commands.guild_only
  @check_staff('kickowania')
  async def cmd_kick(interaction, member: discord.Member):
    await kick(interaction, member)

  @bot.tree.context_menu(name='Skickuj')
  @discord.app_commands.guild_only
  @check_staff('kickowania')
  async def menu_kick(interaction, member: discord.Member):
    await kick(interaction, member)

  async def ban(interaction, user, reason):
    if interaction.user == user:
      await interaction.response.send_message('Nie możesz zbanować samego siebie… 🤨', ephemeral=True)
    elif isinstance(user, discord.Member) and interaction.user.top_role <= user.top_role and interaction.user != interaction.guild.owner:
      await interaction.response.send_message(f'Nie jesteś wyżej w hierarchii od {user.mention}… 🤨', ephemeral=True)
    else:
      try:
        await interaction.guild.ban(user, reason=f'{reason} — {interaction.user.our_name}', delete_message_seconds=0)
      except discord.Forbidden:
        await interaction.response.send_message(f'Nie mam uprawnień, żeby zbanować {user.mention}… 🧐', ephemeral=True)
      else:
        logging.info(f'{interaction.user.id} banned {user.id} for {reason!r}')
        await interaction.response.send_message(f'Pomyślnie zbanowano {user.mention} za `{debacktick(reason)}`. 😒', ephemeral=True, allowed_mentions=discord.AllowedMentions.all())

  @bot.tree.command(name='ban', description='Banuje użytkownika')
  @discord.app_commands.guild_only
  @check_staff('banowania')
  async def cmd_ban(interaction, user: discord.User, reason: str):
    await ban(interaction, user, reason)

  @bot.tree.context_menu(name='Zbanuj')
  # @discord.app_commands.guild_only
  @discord.app_commands.guilds(config['guild']) # HACK: Max number of global context menu commands is 5.
  @check_staff('banowania')
  async def menu_ban(interaction, user: discord.User):
    async def on_submit(interaction2):
      await ban(interaction2, user, text_input.value)

    text_input = discord.ui.TextInput(label='Powód')
    modal = discord.ui.Modal(title=f'Zbanuj {user.our_name}')
    modal.on_submit = on_submit
    modal.add_item(text_input)
    await interaction.response.send_modal(modal)

  async def unban(interaction, user):
    try:
      await interaction.guild.unban(user, reason=f'Na żądanie {interaction.user.our_name}')
      logging.info(f'{interaction.user.id} unbanned {user.id}')
    except discord.NotFound:
      await interaction.response.send_message(f'{user.mention} nie jest obecnie zbanowany… 🤨', ephemeral=True)
    else:
      await interaction.response.send_message(f'Pomyślnie odbanowano {user.mention}! 🥳', ephemeral=True, allowed_mentions=discord.AllowedMentions.all())

  @bot.tree.command(name='unban', description='Odbanowuje użytkownika')
  @discord.app_commands.guild_only
  @check_staff('odbanowywania')
  async def cmd_unban(interaction, user: discord.User):
    await unban(interaction, user)

  @bot.tree.context_menu(name='Odbanuj')
  # @discord.app_commands.guild_only
  @discord.app_commands.guilds(config['guild']) # HACK: Max number of global context menu commands is 5.
  @check_staff('odbanowywania')
  async def menu_unban(interaction, user: discord.User):
    await unban(interaction, user)

  @bot.tree.command(description='Łączy dwa konta tego samego użytkownika')
  @check_staff('łączenia kont')
  async def link(interaction, user1: discord.User, user2: discord.User):
    if user1 == user2:
      await interaction.response.send_message('Nie możesz połączyć tego samego konta z samym sobą… 😐', ephemeral=True)
      return

    with database.lock:
      are_already_linked = user1.id in database.data.get('linked_users', {}).get(user2.id, [])
      if not are_already_linked:
        logging.info(f'Linking users {user1.id} and {user2.id}')
        clique1 = database.data.setdefault('linked_users', {}).setdefault(user1.id, []) + [user1.id]
        clique2 = database.data['linked_users'].setdefault(user2.id, []) + [user2.id]
        for i in clique1:
          database.data['linked_users'][i] += clique2
        for i in clique2:
          database.data['linked_users'][i] += clique1
        database.should_save = True

    if are_already_linked:
      await interaction.response.send_message(f'Konta {user1.mention} i {user2.mention} już są ze sobą połączone… 🤨', ephemeral=True)
    else:
      await interaction.response.send_message(f'Pomyślnie połączono ze sobą konta {user1.mention} i {user2.mention}. 🫡', ephemeral=True)

  @bot.tree.command(description='Odłącza konto od wszystkich innych kont')
  @check_staff('odłączania kont')
  async def unlink(interaction, user: discord.User):
    with database.lock:
      is_already_unlinked = not database.data.get('linked_users', {}).get(user.id, [])
      if not is_already_unlinked:
        logging.info(f'Unlinking user {user.id}')
        for i in database.data['linked_users'][user.id]:
          database.data['linked_users'][i].remove(user.id)
        del database.data['linked_users'][user.id]
        database.should_save = True

    if is_already_unlinked:
      await interaction.response.send_message(f'{user.mention} nie ma żadnych innych kont… 🤨', ephemeral=True)
    else:
      await interaction.response.send_message(f'Pomyślnie odłączono {user.mention} od wszystkich innych kont. 🫡', ephemeral=True)

  @bot.tree.command(description='Wyświetla pozostałe konta użytkownika')
  async def linked(interaction, user: discord.User):
    if not database.data.get('linked_users', {}).get(user.id, []):
      await interaction.response.send_message(f'{user.mention} nie ma żadnych innych kont. 🕵️', ephemeral=True)
    else:
      await interaction.response.send_message(f'Do {user.mention} należą też konta: ' + ', '.join(f'<@{i}>' for i in database.data['linked_users'][user.id]) + '. 🕵️', ephemeral=True)
