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

import console, database
from common import config, format_datetime, is_staff, mention_datetime, debacktick, select_view

bot = None

async def update_roles_for(user):
  roles = [user.guild.get_role(i) for i in config['warn_roles']]
  await user.remove_roles(*roles)
  count = len(database.data.get('warns', {}).get(user.id, []))
  if count > 0 and roles:
    await user.add_roles(roles[min(count, len(roles)) - 1])

async def update_roles():
  for user in bot.get_all_members():
    await update_roles_for(user)

def setup(_bot):
  global bot
  bot = _bot

  @bot.tree.command(description='Warnuje użytkownika')
  async def warn(interaction, user: discord.Member, reason: str):
    if not is_staff(interaction.user):
      await interaction.response.send_message('Nie masz uprawnień do warnowania, tylko administracja może to robić. 😡', ephemeral=True)
      return

    warn = {
      'time': datetime.now().astimezone(),
      'reason': reason,
    }
    database.data.setdefault('warns', {}).setdefault(user.id, []).append(warn)
    database.should_save = True
    count = len(database.data['warns'][user.id])

    await update_roles_for(user)

    await interaction.response.send_message(f'{user.mention} właśnie dostał swojego {count}-ego warna za `{debacktick(reason)}`! 😒')

  @bot.tree.context_menu(name='Odbierz warna')
  async def unwarn(interaction, user: discord.Member):
    if not is_staff(interaction.user):
      await interaction.response.send_message('Nie masz uprawnień do odbierania warnów, tylko administracja może to robić. 😡', ephemeral=True)
      return

    warns = database.data.get('warns', {}).get(user.id, [])

    if not warns:
      await interaction.response.send_message(f'{user.mention} jest grzeczny jak aniołek i nie nazbierał jeszcze żadnych warnów! 😇', ephemeral=True)
      return

    async def callback(interaction2, choice):
      warn = find(int(choice), warns, proj=lambda x: id(x))
      warns.remove(warn)
      database.should_save = True

      await update_roles_for(user)

      reason = debacktick(warn['reason'])
      time = mention_datetime(warn["time"])
      await interaction.edit_original_response(content=f'Pomyślnie odebrano warna `{reason}` z dnia {time} użytkownikowi {user.mention}! 🥳', view=None)

      await interaction2.response.defer()

    select, view = select_view(callback, interaction.user)
    for warn in warns:
      select.add_option(label=warn['reason'], value=id(warn), description=format_datetime(warn["time"]))

    await interaction.response.send_message(f'Którego warna chcesz odebrać użytkownikowi {user.mention}?', view=view)

  @bot.tree.context_menu(name='Pokaż warny')
  async def warns(interaction, user: discord.Member):
    warns = database.data.get('warns', {}).get(user.id, [])
    if warns:
      result = random.choice([
        f'{user.mention} ma już na swoim koncie parę złych uczynków… 😔',
        f'Do {user.mention} nie przyjdzie Mikołaj w tym roku… 😕',
        f'Na {user.mention} czeka już tylko czyściec… 😩',
      ])

      for warn in warns:
        reason = debacktick(warn['reason'])
        time = mention_datetime(warn["time"])
        result += f'\n- `{reason}` w dniu {time}'

      await interaction.response.send_message(result, ephemeral=True)
    else:
      await interaction.response.send_message(f'{user.mention} jest grzeczny jak aniołek i nie nazbierał jeszcze żadnych warnów! 😇', ephemeral=True)

console.begin('warns')
console.register('update_roles', None, 'updates warn roles for all users', lambda: asyncio.run_coroutine_threadsafe(update_roles(), bot.loop).result())
console.end()
