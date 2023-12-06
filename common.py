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

import discord, json, logging

options = {
  'config': 'config.json'
}

config = {
  'token': None,                  # Token twojego bota
  'database': 'database.json',    # Ścieżka do pliku z baza danych
  'autosave': '1m',               # Regularny odstęp czasu, w którym baza danych będzie automatycznie zapisywana, gdy jest to potrzebne
  'console_host': 'localhost',    # Te dwa są w zasadzie oczywiste
  'console_port': 2341,
  'console_hello': 'OOOZet',      # Nazwa wyświetlana w "… says hello!" po połączeniu się z konsolą
  'console_timeout': '1m',        # Czas od ostatniej odebranej komendy, po którym połączenie z konsolą zostanie automatycznie zerwane

  'guild_name': 'OOOZ',           # Nazwa serwera, na którym rezyduje bot
  'staff_roles': [],              # Role, których członkowie należą do administracji
  'alarm_cooldown': '5m',         # Cooldown dla komendy /alarm
  'warn_roles': [],               # Role kosmetyczne wskazujące na liczbę warnów użytkownika
  'counting_channel': None,       # Kanał "#liczenie"
  'xp_cooldown': '1m',            # Odstęp czasu, po którym można ponownie dostać XP
  'xp_min_gain': 15,              # Minimalna ilość XP, którą można dostać za jedną wiadomość
  'xp_max_gain': 40,              # Maksymalna ilość XP, którą można dostać za jedną wiadomość
  'xp_ignored_channels': [],      # Kanały, które nie są liczone do XP
  'xp_ignored_categories': [],    # Kategorie kanałów, które nie są liczone do XP
  'xp_roles': [],                 # Role, które można dostać za poziomy, format to [<poziom>, <rola>]
  'xp_channel': None,             # Kanał na ogłoszenia o kolejnych poziomach zdobywanych przez użytkowników
  'sugestie_channel': None,       # Kanal "#sugestie"
  'sugestie_vote_role': None,     # Rola, która może głosować nad sugestiami
  'sugestie_ping_role': None,     # Rola, która jest pingowana, gdy pojawia się nowa sugestia
  'sugestie_vote_length': '24h',  # Czas na głosowanie nad sugestią
  'sugestie_deciding_lead': None, # Przewaga, po której jedna z opcji wygrywa
}

def load_config():
  logging.info('Loading config')
  try:
    with open(options['config'], 'r') as file:
      global config
      config |= json.load(file)
  except FileNotFoundError:
    raise Exception(f'Config not found: {repr(options["config"])}')

def save_config():
  logging.info('Saving config')
  with open(options['config'], 'w') as file:
    json.dump(config, file, indent=2)

def parse_duration(string):
  units = {
    's': 1,
    'm': 60,
    'h': 60 * 60,
    'd': 60 * 60 * 24,
    'y': 60 * 60 * 24 * 365,
  }
  result = 0
  value = ''
  for c in string + ' ':
    if c.isdigit() or c == '.':
      value += c
    elif c in units and value:
      result += units[c] * (float(value) if '.' in value else int(value))
      value = ''
    elif c.isspace():
      if value:
        result += units['s'] * (float(value) if '.' in value else int(value))
        value = ''
    else:
      raise Exception(f'Invalid duration: {repr(string)}')
  return result

def format_datetime(datetime):
  return datetime.strftime(f'%-d %B %Y %H:%M') # %-d is not portable.

def mention_datetime(datetime):
  return f'<t:{int(datetime.timestamp())}>'

def is_staff(user):
  return any(user.get_role(i) is not None for i in config['staff_roles'])

def mention_message(client, channel, msg):
  return client.get_partial_messageable(channel).get_partial_message(msg).jump_url

def debacktick(string):
  return string.replace('`', '')

def select_view(callback, owner):
  select = discord.ui.Select()
  async def our_callback(interaction):
    await callback(interaction, select.values[0])
  select.callback = our_callback

  view = discord.ui.View()
  view.add_item(select)
  if owner is not None:
    async def interaction_check(interaction):
      return interaction.user == owner
    view.interaction_check = interaction_check

  return select, view

def find(value, iterable, *, proj=lambda x: x):
  return next(filter(lambda x: proj(x) == value, iterable))
