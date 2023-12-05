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

import json, logging

options = {
  'config': 'config.json'
}

config = {
  'token': None,               # Token twojego bota
  'database': 'database.json', # Ścieżka do pliku z baza danych
  'autosave': '1m',            # Regularny odstęp czasu, w którym baza danych będzie automatycznie zapisywana, gdy jest to potrzebne
  'console_host': 'localhost', # Te dwa są w zasadzie oczywiste
  'console_port': 2341,
  'console_hello': 'OOOZet',   # Nazwa wyświetlana w "… says hello!" po połączeniu się z konsolą
  'console_timeout': '1m',     # Czas od ostatniej odebranej komendy, po którym połączenie z konsolą zostanie automatycznie zerwane

  'staff_roles': [],           # Role, których członkowie należą do administracji
  'alarm_cooldown': '5m',      # Cooldown dla komendy /alarm
  'warn_roles': [],            # Role kosmetyczne wskazujące na liczbę warnów użytkownika
  'counting_channel': None,    # Kanał "#liczenie"
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
