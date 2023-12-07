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

import console, database
from common import config, format_datetime, is_staff, mention_datetime, debacktick, select_view, find

bot = None

async def update_roles_for(member):
  logging.info(f'Updating warn roles for {member.id}')
  roles = [member.guild.get_role(i) for i in config['warn_roles']]
  await member.remove_roles(*roles)
  count = len(database.data.get('warns', {}).get(member.id, []))
  if count > 0 and roles:
    await member.add_roles(roles[min(count, len(roles)) - 1])

async def update_roles():
  logging.info('Updating warn roles for all members')
  for member in bot.get_all_members():
    await update_roles_for(member)

def setup(_bot):
  global bot
  bot = _bot

  async def warn(interaction, member, reason):
    if not is_staff(interaction.user):
      await interaction.response.send_message('Nie masz uprawnień do warnowania, tylko administracja może to robić. 😡', ephemeral=True)
      return

    logging.info(f'Adding warn for {member.id} with reason {repr(reason)}')
    warn = {
      'time': datetime.now().astimezone(),
      'reason': reason,
    }
    database.data.setdefault('warns', {}).setdefault(member.id, []).append(warn)
    database.should_save = True

    await update_roles_for(member)

    count = len(database.data['warns'][member.id])
    await interaction.response.send_message(f'{member.mention} właśnie dostał swojego {count}-ego warna za `{debacktick(reason)}`! 😒')

  @bot.tree.command(name='warn', description='Warnuje użytkownika')
  async def cmd_warn(interaction, member: discord.Member, reason: str):
    await warn(interaction, member, reason)

  @bot.tree.context_menu(name='Zwarnuj')
  async def menu_warn(interaction, member: discord.Member):
    async def on_submit(interaction2):
      await warn(interaction2, member, text_input.value)

    text_input = discord.ui.TextInput(label='Powód')
    modal = discord.ui.Modal(title=f'Zwarnuj {member.name}')
    modal.on_submit = on_submit
    modal.add_item(text_input)

    # Maybe we should first check whether the user is staff?
    await interaction.response.send_modal(modal)

  async def unwarn(interaction, member):
    if not is_staff(interaction.user):
      await interaction.response.send_message('Nie masz uprawnień do odbierania warnów, tylko administracja może to robić. 😡', ephemeral=True)
      return

    warns = database.data.get('warns', {}).get(member.id, [])

    if not warns:
      await interaction.response.send_message(f'{member.mention} jest grzeczny jak aniołek i nie nazbierał jeszcze żadnych warnów! 😇', ephemeral=True)
      return

    async def callback(interaction2, choice):
      warn = find(int(choice), warns, proj=lambda x: id(x))

      logging.info(f'Removing warn for {member.id} with reason {repr(warn["reason"])} from {warn["time"]}')
      warns.remove(warn)
      database.should_save = True

      await update_roles_for(member)

      reason = debacktick(warn['reason'])
      time = mention_datetime(warn["time"])
      await interaction.edit_original_response(content=f'Pomyślnie odebrano warna `{reason}` z dnia {time} użytkownikowi {member.mention}! 🥳', view=None)

      await interaction2.response.defer()

    select, view = select_view(callback, interaction.user)
    for warn in warns:
      select.add_option(label=warn['reason'], value=id(warn), description=format_datetime(warn["time"]))

    await interaction.response.send_message(f'Którego warna chcesz odebrać użytkownikowi {member.mention}?', view=view)

  @bot.tree.command(name='unwarn', description='Odbiera warna użytkownikowi')
  async def cmd_unwarn(interaction, member: discord.Member):
    await unwarn(interaction, member)

  @bot.tree.context_menu(name='Odbierz warna')
  async def menu_unwarn(interaction, member: discord.Member):
    await unwarn(interaction, member)

  async def warns(interaction, user):
    warns = database.data.get('warns', {}).get(user.id, [])

    if not warns:
      await interaction.response.send_message(f'{user.mention} jest grzeczny jak aniołek i nie nazbierał jeszcze żadnych warnów! 😇', ephemeral=True)
      return

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

  @bot.tree.command(name='warns', description='Pokazuje warny użytkownika')
  async def cmd_warns(interaction, user: discord.User | None):
    await warns(interaction, interaction.user if user is None else user)

  @bot.tree.context_menu(name='Pokaż warny')
  async def menu_warns(interaction, user: discord.User):
    await warns(interaction, user)

console.begin('warns')
console.register('update_roles', None, 'updates warn roles for all members', lambda: asyncio.run_coroutine_threadsafe(update_roles(), bot.loop).result())
console.end()
