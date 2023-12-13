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

import discord, logging, random
from datetime import datetime

import database
from common import config, hybrid_check, parse_duration
from features import warns, xp

bot = None

def get_staff():
  return {i for role in config['staff_roles'] for i in bot.get_guild(config['guild']).get_role(role).members}

class NoStaffError(discord.app_commands.CheckFailure):
  pass

@hybrid_check
def check_staff_nonempty(interaction):
  if all(not bot.get_guild(config['guild']).get_role(i).members for i in config['staff_roles']):
    raise NoStaffError()

def setup(_bot):
  global bot
  bot = _bot

  @bot.on_check_failure
  async def on_check_failure(interaction, error):
    if isinstance(error, NoStaffError):
      await interaction.response.send_message('Hmm, z jakiegoś powodu nie jest mi znane, żeby ktoś był w administracji… 🤨', ephemeral=True)
    else:
      raise

  @bot.tree.context_menu(name='Odśwież role')
  @discord.app_commands.guilds(config['guild'])
  async def update_roles(interaction, member: discord.Member):
    logging.info(f'Received user request to update roles for {member.id}')
    await interaction.response.defer(ephemeral=True)
    await warns.update_roles_for(member)
    await xp.update_roles_for(member)
    await interaction.followup.send(f'Pomyślnie zaaktualizowano role za warny i XP dla {member.mention}. 👌')

  @bot.listen()
  async def on_member_join(member):
    if member.guild.id != config['guild']:
      return

    logging.info(f'User {member.id} joined the guild')
    await warns.update_roles_for(member)
    await xp.update_roles_for(member)

  @bot.listen()
  async def on_member_remove(member):
    if member.guild.id != config['guild']:
      return

    logging.info(f'User {member.id} left the guild')
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
        await interaction.response.send_message(f'Alarm już zabrzmiał w przeciągu ostatnich **{cooldown}** sekund. ⏱️', ephemeral=True)
        return

    logging.info(f'{interaction.user.id} has raised the alarm!')
    database.data['alarm_last'] = now
    database.should_save = True

    staff = get_staff()
    emoji = random.choice(['😟', '😖', '😱', '😮', '😵', '😵‍💫', '🥴'])
    mentions = ' '.join(i.mention for i in staff)
    await interaction.response.send_message(f'{mentions} Potrzebna natychmiastowa interwencja!!! {emoji}')
    for user in staff:
      guild = bot.get_guild(config['guild'])
      await user.send(f'{interaction.user.mention} potrzebuje natychmiastowej interwencji na **{guild}**!!! {emoji}')
      await user.send('https://c.tenor.com/EDeg5ifIrjQAAAAC/alarm-better-discord.gif')

  @bot.tree.command(description='Wyświetla skład administracji')
  @check_staff_nonempty
  async def staff(interaction):
    result = ''.join(f'- {i.mention}\n' for i in get_staff())
    await interaction.response.send_message(f'W administracji serwera znajdują się: 👮\n{result}', ephemeral=True)
