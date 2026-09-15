# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023-2026 Karol "digitcrusher" Łacina
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

import aiohttp, asyncio, discord, logging, random, string
from discord import app_commands

import database

def get_handle(user):
  return database.data.get('codeforces_handles', {}).get(user)

# TODO: handle stealing others' handles properly
def set_handle(user, value):
  if value is None:
    try:
      del database.data['codeforces_handles'][user]
    except KeyError:
      return False
  else:
    database.data.setdefault('codeforces_handles', {})[user] = value
  database.should_save = True
  return True

codeforces = app_commands.Group(name='codeforces', description='Komendy do nicków na Codeforces')

# TODO: replace this with codeforces's new oauth api
@codeforces.command(name='set', description='Zapamiętuje twój nick na Codeforces')
async def set_(interaction, handle: str):
  logging.info(f'{interaction.user.id} requested to set their Codeforces handle to {handle!r}')

  if any(i not in string.ascii_letters + string.digits + '-._' for i in handle):
    await interaction.response.send_message('Taki nick zawiera niedozwolone znaki… 🤨', ephemeral=True)
    return

  async with aiohttp.ClientSession('https://codeforces.com/api/') as session:
    json = await (await session.get('user.info', params={'handles': handle, 'checkHistoricHandles': 'false'})).json()
  if 'not found' in json.get('comment', ''):
    await interaction.response.send_message('Nie ma na Codeforces konta o takim nicku… 🤨', ephemeral=True)
    return

  a = random.choice(['Agent', 'Legenda', 'Mistrz', 'Pogromca', 'Przyjaciel', 'Zaklinacz', 'Zbawiciel', 'Zjadacz'])
  b = random.choice(['USB', 'Obozów', 'Heur', 'Krokietów', 'Gąsienic', 'Szczurów', 'Kontestów', 'Zadań'])

  # TODO: this could be a relative mention_datetime
  # U+202F is not a word break and allows both words to be selected at once.
  await interaction.response.send_message(f'Aby zweryfikować przynależność tego konta do ciebie, [ustaw swoje imię](https://codeforces.com/settings/social) na `{a}\u202f{b}` w ciągu **{3 * 60} sekund** i czekaj aż do upłynięcia reszty czasu. 🥺', ephemeral=True)
  await asyncio.sleep(3 * 60)

  async with aiohttp.ClientSession('https://codeforces.com/api/') as session:
    json = await (await session.get('user.info', params={'handles': handle, 'checkHistoricHandles': 'false'})).json()
  if json['status'] != 'OK':
    raise Exception(f'Codeforces user info verification request failed: {json["comment"]!r}')
  user_info = json['result'][0]
  handle = user_info['handle']
  first = user_info.get('firstName')
  last = user_info.get('lastName')

  x = ''.join((first or '').split())
  y = ''.join((last or '').split())
  if x == a + b:
    success = ''
  elif y == a + b:
    success = '-# Psst… Miałeś ustawić swoje *imię*, a nie nazwisko. 😉'
  elif x + y == a + b:
    success = '-# Psst… Gratuluję bycia na tyle mądrym, żeby rodzielić hasło weryfikacyjne na imię i nazwisko, mimo iż polecenie kazało ustawić samo imię. 😌'
  else:
    success = None

  if success is not None:
    logging.info(f'{interaction.user.id} has successfully set their Codeforces handle to {handle!r}')
    assert set_handle(interaction.user.id, handle)
    await interaction.edit_original_response(content=f'Pomyślnie zweryfikowano i ustawiono twój nick na Codeforces na `{handle}`! 🥳\n{success}')
  else:
    logging.info(f'{interaction.user.id} failed to verify their Codeforces handle ({first!r} & {last!r} != {a!r} & {b!r})')
    if first is None:
      read = 'end of file'
    elif '`' in first:
      read = 'stringa z grawisami (*ty hakierze*)'
    else:
      read = f'`{first}`'
    await interaction.edit_original_response(content=f'Weryfikacja nie powiodła się. Oczekiwano `{a} {b}`, wczytano {read}. 😕')

async def get(interaction, user):
  handle = get_handle(user.id)
  if handle is None:
    await interaction.response.send_message(f'{user.mention} nie podzielił się jeszcze swoim nickiem na Codeforces. 🕵️', ephemeral=True)
  else:
    await interaction.response.send_message(f'{user.mention} ma nick [`{handle}`](https://codeforces.com/profile/{handle}) na Codeforces. 🕵️', ephemeral=True, suppress_embeds=True)

@codeforces.command(name='get', description='Pokazuje nick użytkownika na Codeforces')
async def cmd_get(interaction, user: discord.User | None):
  await get(interaction, interaction.user if user is None else user)

@app_commands.context_menu(name='Pokaż nick na Codeforces')
async def menu_get(interaction, user: discord.User):
  await get(interaction, user)

@codeforces.command(description='Zapomina twój nick na Codeforces')
async def unset(interaction):
  if set_handle(interaction.user.id, None):
    logging.info(f'{interaction.user.id} has unset their Codeforces handle')
    await interaction.response.send_message('Pomyślnie zapomniano twój nick na Codeforces. 🫡', ephemeral=True)
  else:
    await interaction.response.send_message('Nie podałeś mi jeszcze swojego nicku na Codeforces… 🤨', ephemeral=True)
