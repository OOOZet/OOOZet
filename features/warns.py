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
from dataclasses import dataclass
from datetime import datetime
from dateutil.relativedelta import relativedelta

import console, database
from common import config, debacktick, format_datetime, limit_len, mention_date, mention_datetime, pages_view, select_view
from features.utils import check_staff, is_staff

# TODO: update roles on expire

bot = None

async def update_roles_for(member):
  logging.info(f'Updating warn roles for {member.id}')
  assert member.guild.id == config['guild']
  roles = [discord.Object(i) for i in config['warn_roles']]
  do_expires(member.id)
  await member.remove_roles(*roles)
  count = sum(not warn['expired'] for account in database.data.get('linked_users', {}).get(member.id, []) + [member.id] for warn in database.data['warns'][account])
  if count > 0 and roles:
    await member.add_roles(roles[min(count, len(roles)) - 1])

async def update_roles():
  logging.info('Updating warn roles for all members')
  for member in bot.get_guild(config['guild']).members:
    await update_roles_for(member)

def do_expires(user): # Restarting this algorithm at any point during its execution is corruption-free, so we don't need to acquire database.lock.
  warns = [warn for account in database.data.get('linked_users', {}).get(user, []) + [user] for warn in database.data.get('warns', {}).get(account, [])]
  warns.sort(key=lambda x: x['time'])
  if not warns:
    return

  barriers = []
  for warn in warns:
    barriers.append(warn['time'])
    if warn['expired']:
      barriers.append(warn['expired'])
  barriers.sort()

  interval = relativedelta(**config['warn_expire_interval'])
  now = datetime.now().astimezone()

  time = datetime.fromtimestamp(0).astimezone()
  i = 0
  for warn in warns:
    if warn['expired']:
      continue
    time = max(time, warn['time'])
    while i < len(barriers) and barriers[i] <= time:
      i += 1
    while i < len(barriers) and barriers[i] <= time + interval:
      time = barriers[i]
      i += 1
    time += interval
    if time > now:
      break
    warn['expired'] = time
  database.should_save = True

def do_expires_all():
  for user in database.data.get('warns', {}):
    do_expires(user)

async def setup(_bot):
  global bot
  bot = _bot

  async def warn(interaction, user, reason):
    logging.info(f'Adding warn for {user.id} with reason {reason!r}')
    warn = {
      'time': interaction.created_at,
      'reason': reason,
      'expired': None,
    }
    database.data.setdefault('warns', {}).setdefault(user.id, []).append(warn)
    database.data['warns'][user.id].sort(key=lambda x: x['time'])
    database.should_save = True

    if (member := bot.get_guild(config['guild']).get_member(user.id)) is not None:
      await update_roles_for(member)

    do_expires(user.id)
    count = sum(not warn['expired'] for account in database.data.get('linked_users', {}).get(user.id, []) + [user.id] for warn in database.data['warns'][account])
    await interaction.response.send_message(f'{user.mention} właśnie dostał swoje **{count}-e** ostrzeżenie za `{debacktick(reason)}`! 😒', allowed_mentions=discord.AllowedMentions.all())

  @bot.tree.command(name='warn', description='Ostrzega użytkownika')
  @discord.app_commands.guilds(config['guild'])
  @check_staff('ostrzegania')
  async def cmd_warn(interaction, user: discord.User, reason: str):
    await warn(interaction, user, reason)

  @bot.tree.context_menu(name='Ostrzeż')
  @discord.app_commands.guilds(config['guild'])
  @check_staff('ostrzegania')
  async def menu_warn(interaction, user: discord.User):
    async def on_submit(interaction2):
      await warn(interaction2, user, text_input.value)

    text_input = discord.ui.TextInput(label='Powód')
    modal = discord.ui.Modal(title=f'Ostrzeż {user.our_name}')
    modal.on_submit = on_submit
    modal.add_item(text_input)
    await interaction.response.send_modal(modal)

  async def erase_warn(interaction, user):
    if (user == interaction.user or user.id in database.data.get('linked_users', {}).get(interaction.user.id, [])) and interaction.user != interaction.guild.owner:
      await interaction.response.send_message('Nie możesz usuwać sobie ostrzeżeń. 😒', ephemeral=True)
      return
    elif all(i['expired'] for i in database.data.get('warns', {}).get(user.id, [])):
      await interaction.response.send_message(f'{user.mention} nie ma żadnych niewygasłych ostrzeżeń, które możesz usunąć… 🤨', ephemeral=True)
      return

    async def callback(interaction2, choice):
      warn = next(i for i in database.data['warns'][user.id] if id(i) == int(choice))
      assert not warn['expired']

      logging.info(f'Erasing warn for {user.id} with reason {warn["reason"]!r} from {warn["time"]}')
      database.data['warns'][user.id].remove(warn)
      database.should_save = True

      if (member := bot.get_guild(config['guild']).get_member(user.id)) is not None:
        await update_roles_for(member)

      reason = debacktick(warn['reason'])
      time = mention_datetime(warn['time'])
      await interaction.edit_original_response(content=f'Pomyślnie usunięto ostrzeżenie `{reason}` z dnia {time} użytkownikowi {user.mention}. 🙄', view=None)
      await interaction2.response.defer()

    await interaction.response.send_message(f'Które ostrzeżenie chcesz usunąć użytkownikowi {user.mention}?', view=select_view(
      [
        discord.SelectOption(
          label=limit_len(warn['reason']),
          value=id(warn),
          description=format_datetime(warn['time']),
        )
        for warn in reversed(database.data['warns'][user.id])
      ],
      callback,
      interaction.user,
    ))

  @bot.tree.command(name='erase-warn', description='Usuwa błędnie nadane ostrzeżenie')
  @discord.app_commands.guilds(config['guild'])
  @check_staff('usuwania ostrzeżeń')
  async def cmd_erase_warn(interaction, user: discord.User):
    await erase_warn(interaction, user)

  @bot.tree.context_menu(name='Usuń ostrzeżenie')
  @discord.app_commands.guilds(config['guild'])
  @check_staff('usuwania ostrzeżeń')
  async def menu_erase_warn(interaction, user: discord.User):
    await erase_warn(interaction, user)

  async def warns(interaction, user):
    do_expires(user.id)
    active, expired = [], []
    for account in database.data.get('linked_users', {}).get(user.id, []) + [user.id]:
      for warn in database.data.get('warns', {}).get(account, []):
        if warn['expired']:
          expired.append((warn, account))
        else:
          active.append((warn, account))
    active.sort(key=lambda x: x[0]['time'])
    expired.sort(key=lambda x: x[0]['time'])

    pages = ['']
    def append(line):
      if len(pages[-1]) + len(line) > 2000:
        pages.append('')
      pages[-1] += line

    if active:
      append(random.choice([
        f'{user.mention} ma już na swoim koncie parę złych uczynków… 😔\n',
        f'Do {user.mention} nie przyjdzie Mikołaj w tym roku… 😕\n',
        f'Na {user.mention} czeka już tylko czyściec… 😩\n',
      ]))
      for warn, account in reversed(active):
        reason = debacktick(warn['reason'])
        time = mention_datetime(warn['time'])
        append(f'- `{reason}` w dniu {time}' + (f' na koncie <@{account}>' if account != user.id else '') + '\n')

    if expired and is_staff(interaction.user):
      append(f'Wygasłe ostrzeżenia użytkownika {user.mention}: 📜\n')
      for warn, account in reversed(expired):
        reason = debacktick(warn['reason'])
        time = mention_datetime(warn['time'])
        expired = mention_date(warn['expired'])
        append(f'- `{reason}` z dnia {time} wygasłe {expired}' + (f' na koncie <@{account}>' if account != user.id else '') + '\n')

    if pages == ['']:
      await interaction.response.send_message(f'{user.mention} jest grzeczny jak aniołek i nie nazbierał jeszcze żadnych ostrzeżeń! 😇', ephemeral=True)
      return

    async def on_select_page(interaction2, page):
      await interaction2.response.defer()
      await interaction2.edit_original_response(content=pages[page], view=view)
    view = pages_view(0, len(pages), on_select_page, interaction.user)

    await interaction.response.send_message(pages[0], view=view, ephemeral=True)

  @bot.tree.command(name='warns', description='Pokazuje ostrzeżenia użytkownika')
  async def cmd_warns(interaction, user: discord.User | None):
    await warns(interaction, interaction.user if user is None else user)

  @bot.tree.context_menu(name='Pokaż ostrzeżenia')
  async def menu_warns(interaction, user: discord.User):
    await warns(interaction, user)

console.begin('warns')
console.register('update_roles', None, 'updates warn roles for all members', lambda: asyncio.run_coroutine_threadsafe(update_roles(), bot.loop).result())
console.register('do_expires_all', None, 'applies any pending expires', do_expires_all)
console.end()
