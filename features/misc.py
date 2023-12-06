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

import discord, pprint, random
from datetime import datetime

import database
from common import config, parse_duration
from features import warns, xp

def setup(bot):
  @bot.tree.command(name='config', description='Wyświetla konfigurację bota')
  async def _config(interaction):
    result = config.copy()
    del result['token']
    result = pprint.pformat(result, sort_dicts=False)
    await interaction.response.send_message(f'Moja wewnętrzna konfiguracja wygląda następująco:```json\n{result}```', ephemeral=True)

  @bot.tree.command(description='Dziękuje istotnym twórcom bota')
  async def credits(interaction):
    await interaction.response.send_message('OOOZet powstał dzięki wspólnym staraniom <@671790729676324867>, <@386516541790748673>, <@536253933778370580> i innych. 🙂', ephemeral=True)

  @bot.tree.command(description='Sprawdza ping bota')
  async def ping(interaction):
    await interaction.response.send_message(f'Pong! `{1000 * bot.latency:.0f}ms`', ephemeral=True)

  @bot.tree.command(description='Wzywa administrację po pomoc')
  async def alarm(interaction):
    staff = {i for role in config['staff_roles'] for i in interaction.guild.get_role(role).members}

    if not staff:
      await interaction.response.send_message('Hmm, z jakiegoś powodu nie jest mi znane, żeby ktoś był w administracji… 🤨')
      return

    if 'alarm_last' in database.data:
      now = datetime.now().astimezone()
      cooldown = parse_duration(config['alarm_cooldown'])
      if (now - database.data['alarm_last']).total_seconds() < cooldown:
        await interaction.response.send_message(f'Alarm już zabrzmiał w przeciągu ostatnich {cooldown} sekund. ⏱️', ephemeral=True)
        return
      database.data['alarm_last'] = now
      database.should_save = True

    emoji = random.choice(['😟', '😖', '😱', '😮', '😵', '😵‍💫', '🥴'])

    mentions = ' '.join(i.mention for i in staff)
    await interaction.response.send_message(f'{mentions} Potrzebna natychmiastowa interwencja!!! {emoji}')

    for user in staff:
      await user.send(f'{interaction.user.mention} potrzebuje natychmiastowej interwencji na {config["guild_name"]}!!! {emoji}')
      await user.send('https://c.tenor.com/EDeg5ifIrjQAAAAC/alarm-better-discord.gif')

  @bot.tree.context_menu(name='Odśwież role')
  async def update_roles(interaction, user: discord.User):
    await warns.update_roles_for(user)
    await xp.update_roles_for(user)
    await interaction.response.send_message(f'Pomyślnie zaaktualizowano role za warny i XP dla {user.mention}. 👌', ephemeral=True)

  @bot.listen()
  async def on_member_join(user):
    await warns.update_roles_for(user)
    await xp.update_roles_for(user)
