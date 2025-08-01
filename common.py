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

import asyncio, discord, json, logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

options = {
  'config': 'config.json',
  'debug': False,
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
  'timezone': 'Europe/Warsaw',               # Strefa czasowa IANA, w której żyje społeczność

  'alarm_cooldown': '5m',                    # Cooldown dla komendy /alarm
  'timeout_role': None,                      # Rola kosmetyczna pokazująca, czy użytkownik ma timeouta
  'timeout_poll_rate': '1m',                 # Częstotliwość sprawdzania wygaśnięcia timeoutów
  'media_channels': [],                      # Kanały, na które można wysyłać tylko zdjęcia i filmy

  'warn_roles': [],                          # Role kosmetyczne wskazujące na liczbę warnów użytkownika
  'warn_expire_interval': { 'months': 1 },   # Obiekt relativedelta określający odstęp czasu od ostatniej zmianie w liczbie warnów użytkownika, po którym wygasa najstarszy warn
  'counting_channel': None,                  # Kanał "#liczenie"
  'fajne_zadanka_channel': None,             # Kanał, na który użytkownicy mogą wysyłać linki do zadań algorytmicznych

  'xp_cooldown': '1m',                       # Odstęp czasu, po którym można ponownie dostać XP
  'xp_min_gain': 15,                         # Minimalna ilość XP, którą można dostać za jedną wiadomość
  'xp_max_gain': 40,                         # Maksymalna ilość XP, którą można dostać za jedną wiadomość
  'xp_ignored_channels': [],                 # Kanały, które nie są liczone do XP
  'xp_ignored_categories': [],               # Kategorie kanałów, które nie są liczone do XP
  'xp_unignored_channels': [],               # Wyjątki do powyższego
  'xp_roles': [],                            # Role, które można dostać za poziomy, format to [<poziom>, <rola>]
  'xp_channel': None,                        # Kanał na ogłoszenia o kolejnych poziomach zdobywanych przez użytkowników

  'sugestie_channel': None,                  # Kanał "#sugestie"
  'sugestie_role': None,                     # Rola, która może opiniować i głosować nad sugestiami
  'sugestie_review_ping_role': None,         # Rola, która jest pingowana, gdy pojawia się nowa sugestia
  'sugestie_review_length': '1d',            # Czas na opiniowanie sugestii
  'sugestie_vote_ping_role': None,           # Rola, która jest pingowana, gdy zaczyna się głosowanie nad sugestią
  'sugestie_vote_length': '1d',              # Czas na głosowanie nad sugestią

  'websub_host': None,                       # Adres tego serwera
  'websub_port': 13579,                      # Port, na którym będzie odpalony serwer WebSub
  'websub_lease_time': '1d',                 # Domyślny czas ważności subskrypcji WebSub
  'websub_sub_retries': [                    # Opóźnienia kolejnych prób zasubskrybowania
    '5s', '15s', '30s', '1m',
    '5m', '15m', '30m', '1h'
  ],
  'websub_timeout': '1m',                    # Maksymalny czas oczekiwania na subskrypcję i weryfikację subskrypcji

  'oki_channel': None,                       # Kanał, na który są wysyłane ogłoszenia o transmisjach na żywo i nowych filmach OKI
  'oki_role': None,                          # Rola, która jest pingowana przy każdym ogłoszeniu o nowym filmie lub transmisji
  'oki_youtube': 'UCw1Z4iA0T-QNaJ-sEOXeYCw', # ID (a nie nazwa użytkownika) kanału YouTube
  'youtube_advance': '15m',                  # Wyprzedzenie, z którym są wysyłane ogłoszenia o transmisjach
  'youtube_api_key': None,                   # Klucz dewelopera do API YouTube

  'codeforces_channel': None,                # Kanał, na który są wysyłane przypomnienia o rundach na Codeforces
  'codeforces_role': None,                   # Rola, która jest pingowana w przypomnieniach o rundach
  'codeforces_advance': '15m',               # Wyprzedzenie, z którym są wysyłane przypomnienia o rundach
  'codeforces_poll_rate': '1h',              # Częstotliwość aktualizowania listy rund

  'atcoder_channel': None,                   # Kanał, na który są wysyłane przypomnienia o kontestach na AtCoder
  'atcoder_role': None,                      # Rola, która jest pingowana w przypomnieniach o kontestach
  'atcoder_advance': '15m',                  # Wyprzedzenie, z którym są wysyłane przypomnienia o kontestach
  'atcoder_poll_rate': '1d',                 # Częstotliwość aktualizowania listy kontestów

  'help_forum_channel': None,                # Forum, na którym użytkownicy pytają o pomoc z zadaniami
  'help_forum_ping_channel': None,           # Kanał, na który są wysyłane wezwania do pomocy na forum
  'help_forum_ping_role': None,              # Rola, która jest pingowana w wezwaniach do pomocy na forum
  'help_forum_award_role': None,             # Rola dla najbardziej pomocnych pomagaczy
  'help_forum_award_count': 3,               # Liczba nagradzanych pomagaczy
  'help_forum_eval_max_age': '1y',           # Maksymalny wiek postów branych pod uwagę w rankingu pomagaczy
  'help_forum_contrib_cooldown': '1m',       # Odstęp czasu, po którym można ponownie dostać punkt udziału w rozwiązywaniu pytania
  'help_forum_eval_rate': '1d',              # Częstotliwość aktualizowania rankingu pomagaczy

  'ping_race_role': None,                    # Rola pingowana w konkursie na najszybszy ping dnia
  'ping_race_hour': 21,                      # Godzina, o której należy spingować tę rolę
  'ping_race_minute': 37,                    # Minuta, o której należy spingować tę rolę
  'ping_race_max_age_days': 90,              # Maksymalny wiek pingów branych pod uwagę w rankingu
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

def mention_date(datetime):
  return f'<t:{int(datetime.timestamp())}:D>'

def mention_message(client, channel, msg):
  return client.get_partial_messageable(channel).get_partial_message(msg).jump_url

def debacktick(string):
  return string.replace('`', '')

def pages_view(init_page, pagec, on_select_page, owner):
  view = discord.ui.View()
  async def interaction_check(interaction):
    return interaction.user == owner
  view.interaction_check = interaction_check

  if pagec <= 1:
    return view

  curr_page = init_page
  async def select(interaction, page):
    nonlocal curr_page
    curr_page = page
    refresh()
    await on_select_page(interaction, curr_page)

  first = discord.ui.Button(label='⇤')
  async def callback(interaction):
    await select(interaction, 0)
  first.callback = callback
  view.add_item(first)

  prev = discord.ui.Button(label='←')
  async def callback(interaction):
    await select(interaction, curr_page - 1)
  prev.callback = callback
  view.add_item(prev)

  indicator = discord.ui.Button(disabled=True)
  view.add_item(indicator)

  next = discord.ui.Button(label='→')
  async def callback(interaction):
    await select(interaction, curr_page + 1)
  next.callback = callback
  view.add_item(next)

  last = discord.ui.Button(label='⇥')
  async def callback(interaction):
    await select(interaction, pagec - 1)
  last.callback = callback
  view.add_item(last)

  def refresh():
    first.disabled = curr_page == 0
    prev.disabled = curr_page - 1 < 0
    indicator.label = f'Strona {curr_page + 1} z {pagec}'
    next.disabled = curr_page + 1 >= pagec
    last.disabled = curr_page == pagec - 1
  refresh()

  return view

def select_view(select_options, callback, owner):
  view = discord.ui.View()
  async def interaction_check(interaction):
    return interaction.user == owner
  view.interaction_check = interaction_check

  select = discord.ui.Select()
  async def our_callback(interaction):
    await callback(interaction, select.values[0])
  select.callback = our_callback
  select.options = select_options[:25]
  view.add_item(select)

  async def refresh(interaction, page):
    await interaction.response.defer()
    select.options = select_options[25 * page : 25 * (page + 1)]
    await interaction.edit_original_response(view=view)
  for i in pages_view(0, (len(select_options) + 25 - 1) // 25, refresh, None).children:
    view.add_item(i)

  return view

@dataclass
class HybridCheck:
  pred: Callable[[discord.Interaction], bool]
  is_consistent: bool # Makes the check be taken into account in /help

  def __call__(self, *args, **kwargs):
    return self.pred(*args, **kwargs) is not False

def hybrid_check(*, is_consistent=False):
  def decorator(pred):
    check = HybridCheck(pred, is_consistent)
    def decorator_or_pred(arg=None):
      if arg is None or isinstance(arg, discord.Interaction):
        return check(arg)
      else:
        return discord.app_commands.check(check)(arg)
    return decorator_or_pred
  return decorator

discord.User.our_name = discord.Member.our_name = property(lambda self: self.name + ('#' + self.discriminator if self.discriminator != '0' else ''))

def limit_len(string): # Used primarily for labels in select views
  return string if len(string) <= 100 else string[:99] + '…'

async def sleep_until(time):
  while (now := datetime.now().astimezone()) < time:
    await asyncio.sleep(min((time - now).total_seconds(), 3 * 60))
