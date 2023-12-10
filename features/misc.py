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
from common import config, parse_duration
from features import warns, xp

def setup(bot):
  @bot.tree.context_menu(name='Odśwież role')
  async def update_roles(interaction, member: discord.Member):
    logging.info(f'Received user request to update roles for {member.id}')
    await interaction.response.defer(ephemeral=True)
    await warns.update_roles_for(member)
    await xp.update_roles_for(member)
    await interaction.followup.send(f'Pomyślnie zaaktualizowano role za warny i XP dla {member.mention}. 👌')

  @bot.listen()
  async def on_member_join(member):
    logging.info(f'User {member.id} joined the guild')
    await warns.update_roles_for(member)
    await xp.update_roles_for(member)

  @bot.listen()
  async def on_member_remove(member):
    logging.info(f'User {member.id} left the guild')
    if member.guild.system_channel_flags.join_notifications:
      announcement = random.choice([
        f'Niestety nie ma już {member.mention} z nami… 🕯️',
        f'Chwila ciszy dla {member.mention}… 🕯️',
        f'{member.mention} już nie mógł wytrzymać tego syfu i wyszedł… 🕯️',
        f'{member.mention} wyszedł z serwera… 🕯️',
      ])
      await member.guild.system_channel.send(announcement)

  @bot.tree.command(description='Wzywa administrację po pomoc')
  async def alarm(interaction):
    staff = {i for role in config['staff_roles'] for i in interaction.guild.get_role(role).members}

    if not staff:
      await interaction.response.send_message('Hmm, z jakiegoś powodu nie jest mi znane, żeby ktoś był w administracji… 🤨')
      return

    now = datetime.now().astimezone()
    if 'alarm_last' in database.data:
      cooldown = parse_duration(config['alarm_cooldown'])
      if (now - database.data['alarm_last']).total_seconds() < cooldown:
        await interaction.response.send_message(f'Alarm już zabrzmiał w przeciągu ostatnich {cooldown} sekund. ⏱️', ephemeral=True)
        return

    logging.info(f'{interaction.user.id} has raised the alarm!')
    database.data['alarm_last'] = now
    database.should_save = True

    emoji = random.choice(['😟', '😖', '😱', '😮', '😵', '😵‍💫', '🥴'])

    mentions = ' '.join(i.mention for i in staff)
    await interaction.response.send_message(f'{mentions} Potrzebna natychmiastowa interwencja!!! {emoji}')

    for user in staff:
      await user.send(f'{interaction.user.mention} potrzebuje natychmiastowej interwencji na {config["guild_name"]}!!! {emoji}')
      await user.send('https://c.tenor.com/EDeg5ifIrjQAAAAC/alarm-better-discord.gif')

  @bot.tree.command(description='Wyświetla skład administracji')
  async def staff(interaction):
    staff = {i for role in config['staff_roles'] for i in interaction.guild.get_role(role).members}

    if not staff:
      await interaction.response.send_message('Hmm, z jakiegoś powodu nie jest mi znane, żeby ktoś był w administracji… 🤨')
      return

    await interaction.response.send_message('W administracji tego serwera znajdują się: 👮\n' + ''.join(f'- {i.mention}\n' for i in staff), ephemeral=True)
