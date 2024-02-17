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
  'token': None,                             # Token twojego bota
  'database': 'database.json',               # Ścieżka do pliku z baza danych
  'autosave': '1m',                          # Regularny odstęp czasu, w którym baza danych będzie automatycznie zapisywana, gdy jest to potrzebne
  'console_host': 'localhost',               # Te dwa są w zasadzie oczywiste
  'console_port': 2341,
  'console_hello': 'OOOZet',                 # Nazwa wyświetlana w "… says hello!" po połączeniu się z konsolą
  'console_timeout': '1m',                   # Czas od ostatniej odebranej komendy, po którym połączenie z konsolą zostanie automatycznie zerwane

  'guild': None,                             # Serwer, na którym rezyduje bot
  'staff_roles': [],                         # Role, których członkowie należą do administracji
  'server_maintainer': None,                 # ID osoby odpowiedzialnej za logi bota

  'alarm_cooldown': '5m',                    # Cooldown dla komendy /alarm
  'warn_roles': [],                          # Role kosmetyczne wskazujące na liczbę warnów użytkownika
  'counting_channel': None,                  # Kanał "#liczenie"

  'xp_cooldown': '1m',                       # Odstęp czasu, po którym można ponownie dostać XP
  'xp_min_gain': 15,                         # Minimalna ilość XP, którą można dostać za jedną wiadomość
  'xp_max_gain': 40,                         # Maksymalna ilość XP, którą można dostać za jedną wiadomość
  'xp_ignored_channels': [],                 # Kanały, które nie są liczone do XP
  'xp_ignored_categories': [],               # Kategorie kanałów, które nie są liczone do XP
  'xp_roles': [],                            # Role, które można dostać za poziomy, format to [<poziom>, <rola>]
  'xp_channel': None,                        # Kanał na ogłoszenia o kolejnych poziomach zdobywanych przez użytkowników

  'sugestie_channel': None,                  # Kanal "#sugestie"
  'sugestie_vote_role': None,                # Rola, która może głosować nad sugestiami
  'sugestie_ping_role': None,                # Rola, która jest pingowana, gdy pojawia się nowa sugestia
  'sugestie_vote_length': '1d',              # Czas na głosowanie nad sugestią
  'sugestie_deciding_lead': None,            # Przewaga, po której jedna z opcji wygrywa
  'sugestie_autoupdate': '1h',               # Regularny odstęp czasu, w którym trwające sugestie są automatycznie aktualizowane

  'websub_host': None,                       # Adres tego serwera
  'websub_port': 13579,                      # Port, na którym będzie odpalony serwer WebSub
  'websub_lease_time': '7d',                 # Domyślny czas ważności subskrypcji WebSub
  'websub_sub_retries': [                    # Opóźnienia kolejnych prób zasubskrybowania
    '5s', '15s', '30s', '1m',
    '5m', '15m', '30m', '1h'
  ],
  'websub_timeout': '1m',                    # Maksymalny czas oczekiwania na subskrypcję i weryfikację subskrypcji

  'oki_channel': None,                       # Kanał, na który są wysyłane ogłoszenia o transmisjach na żywo i nowych filmach OKI
  'oki_role': None,                          # Rola, która jest pingowana przy każdym ogłoszeniu o nowym filmie lub transmisji
  'oki_youtube': 'UCw1Z4iA0T-QNaJ-sEOXeYCw', # ID (a nie nazwa użytkownika) kanału YouTube
  'youtube_api_key': None,                   # Klucz dewelopera do API YouTube
  'youtube_timeout': '1m',                   # Maksymalny czas oczekiwania na odpowiedź od serwera YouTube
  'codeforces_channel': None,                # Kanał, na który są wysyłane przypomnienia o rundach na Codeforces
  'codeforces_role': None,                   # Rola, która jest pingowana w przypomnieniach o rundach
  'codeforces_advance': '15m',               # Wyprzedzenie, z którym są wysyłane przypomnienia o rundach
  'codeforces_poll_rate': '1d',              # Częstotliwość aktualizowania listy rund
  'codeforces_timeout': '5m',                # Maksymalny czas oczekiwania na odpowiedź od serwera Codeforces
}

def redacted_config():
  result = config.copy()
  result['token'] = result['websub_host'] = result['youtube_api_key'] = '[hidden]'
  return result

def load_config():
  logging.info('Loading config')
  try:
    with open(options['config'], 'r') as file:
      global config
      config |= json.load(file)
  except FileNotFoundError:
    raise Exception(f'Config not found: {options["config"]!r}')

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
      raise Exception(f'Invalid duration: {string!r}')
  return result

def format_datetime(datetime):
  return datetime.strftime('%-d %B %Y %H:%M') # %-d is not portable.

def mention_datetime(datetime, *, relative=False):
  timestamp = int(datetime.timestamp())
  return f'<t:{timestamp}:R>' if relative else f'<t:{timestamp}>'

def mention_message(client, channel, msg):
  return client.get_partial_messageable(channel).get_partial_message(msg).jump_url

def debacktick(string):
  return string.replace('`', '')

def select_view(callback, owner=None):
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

def hybrid_check(pred):
  def our_pred(interaction):
    if pred(interaction) is False:
      return False
    return True
  def decorator_or_pred(arg=None):
    if arg is None or isinstance(arg, discord.Interaction):
      return our_pred(arg)
    else:
      return discord.app_commands.check(our_pred)(arg)
  return decorator_or_pred

discord.User.our_name = discord.Member.our_name = property(fget=lambda self: self.name + ('#' + self.discriminator if self.discriminator != '0' else ''))

def limit_len(string): # Used primarily for labels in select views
  return string if len(string) <= 100 else string[:99] + '…'
