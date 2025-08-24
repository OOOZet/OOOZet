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

import aiohttp, asyncio, discord, logging, random, string
from dataclasses import dataclass
from datetime import datetime, timezone

import console, database
from common import config, debacktick, mention_datetime, parse_duration

bot = None

@dataclass
class Contest:
  id: int
  title: str
  time: datetime

  @staticmethod
  def from_json(json):
    return Contest(
      json['id'],
      json['name'],
      datetime.fromtimestamp(json['startTimeSeconds'], timezone.utc),
    )

  @property
  def link(self):
    return f'https://codeforces.com/contest/{self.id}'

  @property
  def is_niche(self):
    return all(i not in self.title for i in ['Round', 'Hello', 'Good Bye'])

async def send_national_standings(contest):
  logging.info(f'Sending national standings for Codeforces contest {contest.id}')

  if config['codeforces_channel'] is None:
    return

  async with aiohttp.ClientSession() as session:
    json = await (await session.get(f'https://codeforces.com/api/contest.ratingChanges?contestId={contest.id}')).json()
  if json['status'] != 'OK':
    if json['comment'] != 'contestId: Rating changes are unavailable for this contest':
      logging.error(f'Codeforces contest rating changes request failed: {json["comment"]!r}')
      return True
  elif not json['result']:
    logging.error('Codeforces contest rating changes are not available yet')
    return True
  rating_changes = {i['handle']: i for i in json.get('result', [])}

  async with aiohttp.ClientSession() as session:
    standings = await (await session.get(f'https://codeforces.com/api/contest.standings?contestId={contest.id}&participantTypes=CONTESTANT,OUT_OF_COMPETITION')).json()
  if standings['status'] != 'OK':
    logging.error(f'Codeforces contest standings request failed: {standings["comment"]!r}')
    return True

  user_infos = {}

  handles = [member['handle'] for entry in standings['result']['rows'] for member in entry['party']['members']]
  # Codeforces's documentation says we are allowed to write in as many as
  # 10'000 users but it seems like their infrastructure fails anyway for any
  # count of at least around 700 users.
  for i in range(0, len(handles), 600):
    batch = handles[i : i + 600]

    async with aiohttp.ClientSession() as session:
      json = await (await session.get('https://codeforces.com/api/user.info?handles=' + ';'.join(batch))).json()
    if json['status'] != 'OK':
      logging.error(f'Codeforces user info request failed: {json["comment"]!r}')
      return True

    assert len(batch) == len(json['result'])
    user_infos.update(zip(batch, json['result']))

  lines = []

  reverse_handles = {v: k for k, v in database.data.get('codeforces_handles', {}).items()}
  for entry in standings['result']['rows']:
    team = [member['handle'] for member in entry['party']['members']]

    if not all(user_infos[i].get('country') == 'Poland' for i in team):
      continue

    line = f'{len(lines) + 1}. #{entry["rank"]} ' + ', '.join(
      f'<@{reverse_handles[handle]}>' if handle in reverse_handles else f'[{handle}](https://codeforces.com/profile/{handle})'
      # contest.standings/contest.ratingChanges sometimes contains outdated handles. :rolling_eyes:
      for handle in map(lambda x: user_infos[x]['handle'], team)
    )
    if len(team) == 1 and team[0] in rating_changes:
      old = rating_changes[team[0]]["oldRating"]
      new = rating_changes[team[0]]["newRating"]
      line += f' {old} → {new}'
      delta = new - old
      if delta > 0:
        line += f' **({delta:+})**'
      else:
        line += f' ({delta:+})'
    line += '\n'
    lines.append(line)

  await bot.wait_until_ready()
  channel = bot.get_channel(config['codeforces_channel'])
  header = f'Ranking zawodników z Polski w [{contest.title}]({contest.link}): 🏆 🇵🇱\n'

  if not lines:
    await channel.send(header, suppress_embeds=True)
    await channel.send('https://tenor.com/view/tumbleweed-desert-awkward-silence-heat-wave-crickets-gif-24664698')
    return

  lines.insert(0, header)
  while lines:
    cnt = 1
    size = len(lines[0])
    while cnt < len(lines) and size + len(lines[cnt]) <= 2000:
      size += len(lines[cnt])
      cnt += 1
    await channel.send(''.join(lines[:cnt]), suppress_embeds=True)
    del lines[:cnt]

async def setup(_bot):
  global bot
  bot = _bot

  async def remind(contest, delay):
    logging.info(f'Setting reminder for Codeforces contest {contest.id} for {delay} seconds')
    await asyncio.sleep(delay)
    logging.info(f'Reminding about Codeforces contest {contest.id}')

    if config['codeforces_channel'] is None:
      return

    if not contest.is_niche and config['codeforces_role'] is not None:
      mention = f'<@&{config["codeforces_role"]}>'
    else:
      mention = ''
    relative_time = mention_datetime(contest.time, relative=True)
    await bot.get_channel(config['codeforces_channel']).send(f'{mention} [{contest.title}]({contest.link}) zaczyna się {relative_time}! 🔔', allowed_mentions=discord.AllowedMentions.all(), suppress_embeds=True)

  reminders = []
  watchlist = set()

  @discord.ext.tasks.loop(seconds=parse_duration(config['codeforces_poll_rate']))
  async def poll():
    logging.info('Periodically downloading Codeforces contest list')

    async with aiohttp.ClientSession() as session:
      json = await (await session.get('https://codeforces.com/api/contest.list')).json()
    if json['status'] != 'OK':
      logging.error(f'Codeforces contest list request failed: {json["comment"]!r}')
      return

    for task in reminders:
      task.cancel()
    reminders.clear()

    for entry in json['result']:
      contest = Contest.from_json(entry)

      if entry['phase'] == 'BEFORE':
        delay = -entry['relativeTimeSeconds'] - parse_duration(config['codeforces_advance'])
        if delay > 0:
          reminders.append(asyncio.create_task(remind(contest, delay)))

      if entry['phase'] != 'FINISHED':
        logging.info(f'Adding Codeforces contest {contest.id} to watchlist')
        watchlist.add(contest.id)
      elif contest.id in watchlist:
        if not await send_national_standings(contest):
          watchlist.remove(contest.id)

  poll.start()

  codeforces = discord.app_commands.Group(name='codeforces', description='Komendy do nicków na Codeforces')
  bot.tree.add_command(codeforces)

  @codeforces.command(name='set', description='Zapamiętuje twój nick na Codeforces')
  async def set_(interaction, handle: str):
    logging.info(f'{interaction.user.id} requested to set their Codeforces handle to {handle!r}')

    if any(i not in string.ascii_letters + string.digits + '-._' for i in handle):
      await interaction.response.send_message('Taki nick zawiera niedozwolone znaki… 🤨', ephemeral=True)
      return

    async with aiohttp.ClientSession() as session:
      json = await (await session.get(f'https://codeforces.com/api/user.info?handles={handle}&checkHistoricHandles=false')).json()
    if 'not found' in json.get('comment', ''):
      await interaction.response.send_message('Nie ma na Codeforces konta o takim nicku… 🤨', ephemeral=True)
      return

    a = random.choice(['Agent', 'Legenda', 'Mistrz', 'Pogromca', 'Przyjaciel', 'Zaklinacz', 'Zbawiciel', 'Zjadacz'])
    b = random.choice(['USB', 'Obozów', 'Heur', 'Krokietów', 'Gąsienic', 'Szczurów', 'Kontestów', 'Zadań'])

    # U+202F is not a word break and allows both words to be selected at once.
    await interaction.response.send_message(f'Aby zweryfikować przynależność tego konta do ciebie, [ustaw swoje imię](https://codeforces.com/settings/social) na `{a}\u202f{b}` w ciągu **{3 * 60} sekund** i czekaj aż do upłynięcia reszty czasu. 🥺', ephemeral=True)
    await asyncio.sleep(3 * 60)

    async with aiohttp.ClientSession() as session:
      json = await (await session.get(f'https://codeforces.com/api/user.info?handles={handle}&checkHistoricHandles=false')).json()
    if json['status'] != 'OK':
      raise Exception(f'Codeforces user info verification request failed: {json["comment"]!r}')
    first = json['result'][0].get('firstName')
    last = json['result'][0].get('lastName')

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
      database.data.setdefault('codeforces_handles', {})[interaction.user.id] = handle
      database.should_save = True
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
    handle = database.data.get('codeforces_handles', {}).get(user.id)
    if handle is None:
      await interaction.response.send_message(f'{user.mention} nie podzielił się jeszcze swoim nickiem na Codeforces. 🕵️', ephemeral=True)
    else:
      await interaction.response.send_message(f'{user.mention} ma nick [`{handle}`](https://codeforces.com/profile/{handle}) na Codeforces. 🕵️', ephemeral=True, suppress_embeds=True)

  @codeforces.command(name='get', description='Pokazuje nick użytkownika na Codeforces')
  async def cmd_get(interaction, user: discord.User | None):
    await get(interaction, interaction.user if user is None else user)

  @bot.tree.context_menu(name='Pokaż nick na Codeforces')
  async def menu_get(interaction, user: discord.User):
    await get(interaction, user)

  @codeforces.command(description='Zapomina twój nick na Codeforces')
  async def unset(interaction):
    try:
      del database.data['codeforces_handles'][interaction.user.id]
      database.should_save = True
    except KeyError:
      await interaction.response.send_message('Nie podałeś mi jeszcze swojego nicku na Codeforces… 🤨', ephemeral=True)
    else:
      logging.info(f'{interaction.user.id} has unset their Codeforces handle')
      await interaction.response.send_message('Pomyślnie zapomniano twój nick na Codeforces. 🫡', ephemeral=True)

async def send_standings(contest_id):
  async with aiohttp.ClientSession() as session:
    json = await (await session.get(f'https://codeforces.com/api/contest.standings?contestId={contest_id}&count=1')).json()
  if json['status'] != 'OK':
    raise Exception(f'Codeforces contest standings request failed: {json["comment"]!r}')
  await send_national_standings(Contest.from_json(json['result']['contest']))

console.begin('codeforces')
console.register('send_standings', '<id>', 'send the standings of Polish contestants in a Codeforces contest', lambda x: asyncio.run_coroutine_threadsafe(send_standings(int(x)), bot.loop).result())
console.end()
