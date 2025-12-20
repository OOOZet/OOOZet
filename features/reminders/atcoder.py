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
from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime, timedelta

import console, database
from common import config, mention_datetime, parse_duration, sleep_until

bot = None

@dataclass
class Contest:
  id: str
  title: str
  time: datetime

  @property
  def link(self):
    return f'https://atcoder.jp/contests/{self.id}'

  @property
  def is_niche(self):
    return all(i not in self.title for i in ['Beginner', 'Regular', 'Grand'])

async def get(session, url):
  while True:
    response = await session.get(url)
    if response.status != 429:
      response.raise_for_status()
      return response
    seconds = int(response.headers['Retry-After'])
    logging.info(f'Rate limited by {response.url.host}. Retrying in {seconds} seconds')
    await asyncio.sleep(seconds)

async def send_national_standings(contest):
  logging.info(f'Sending national standings for AtCoder contest {contest.id}')

  if config['atcoder_channel'] is None:
    return

  standings = []

  async with aiohttp.ClientSession() as session:
    url_suffix = f'&format=json&api_key={config["clist_api_key"]}&username={config["clist_username"]}'

    json = await (await get(session, f'https://clist.by/api/v4/contest/?resource_id=93&event={contest.title}{url_suffix}')).json()
    if len(json['objects']) != 1:
      raise Exception(f'No unique contest in {json!r}')
    clist_id = json['objects'][0]['id']

    url = f'/api/v4/statistics/?contest_id={clist_id}&with_more_fields=true&place__isnull=false&order_by=place&limit=1000000{url_suffix}'
    while url:
      url = 'https://clist.by' + url
      json = await (await get(session, url)).json()
      standings += json['objects']
      url = json['meta']['next']

  if all(entry['rating_change'] is None for entry in standings):
    raise Exception('Rating changes are not available yet')

  lines = []

  reverse_handles = {v: k for k, v in database.data.get('atcoder_handles', {}).items()}
  for entry in standings:
    if entry['more_fields'].get('country') != 'PL':
      continue

    line = f'{len(lines) + 1}. #{entry["place"]}'
    handle = entry['handle']
    if handle in reverse_handles:
      line += f' <@{reverse_handles[handle]}>'
    else:
      line += f' [{handle}](https://atcoder.jp/users/{handle})'
    delta = entry['rating_change']
    if delta is not None:
      line += f' {entry["old_rating"]} → {entry["new_rating"]}'
      if delta > 0:
        line += f' **({delta:+})**'
      else:
        line += f' ({delta:+})'
    line += '\n'
    lines.append(line)

  await bot.wait_until_ready()
  channel = bot.get_channel(config['atcoder_channel'])
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

  async def remind(contest):
    time = contest.time - timedelta(seconds=parse_duration(config['atcoder_advance']))
    logging.info(f'Setting reminder for AtCoder contest {contest.id} for {time}')
    await sleep_until(time)
    logging.info(f'Reminding about AtCoder contest {contest.id}')

    if config['atcoder_channel'] is None:
      return

    if not contest.is_niche and config['atcoder_role'] is not None:
      mention = f'<@&{config["atcoder_role"]}>'
    else:
      mention = ''
    relative_time = mention_datetime(contest.time, relative=True)
    await bot.get_channel(config['atcoder_channel']).send(f'{mention} [{contest.title}]({contest.link}) zaczyna się {relative_time}! 🔔', allowed_mentions=discord.AllowedMentions.all(), suppress_embeds=True)

  reminders = []
  watchlist = set()

  @discord.ext.tasks.loop(seconds=parse_duration(config['atcoder_poll_rate']))
  async def poll():
    logging.info('Periodically downloading AtCoder contest schedule')

    async with aiohttp.ClientSession(raise_for_status=True) as session:
      text = await (await session.get('https://atcoder.jp/contests/')).text()
    html = BeautifulSoup(text, 'lxml')
    entries = html.find(id='contest-table-upcoming').tbody.find_all('tr')
    entries += html.find(id='contest-table-recent').tbody.find_all('tr')

    for task in reminders:
      task.cancel()
    reminders.clear()

    for entry in entries:
      entry = entry.find_all('td')
      contest = Contest(
        entry[1].a['href'].removeprefix('/contests/'),
        entry[1].a.text.strip(),
        datetime.fromisoformat(entry[0].text),
      )

      if datetime.now().astimezone() < contest.time - timedelta(seconds=parse_duration(config['atcoder_advance'])):
        reminders.append(asyncio.create_task(remind(contest)))

        logging.info(f'Adding AtCoder contest {contest.id} to watchlist')
        watchlist.add(contest.id)

      elif contest.id in watchlist:
        try:
          await send_national_standings(contest)
        except:
          logging.exception('Got exception while sending AtCoder national standings')
        else:
          watchlist.remove(contest.id)

  poll.start()

  atcoder = discord.app_commands.Group(name='atcoder', description='Komendy do nicków na AtCoder')
  bot.tree.add_command(atcoder)

  @atcoder.command(name='set', description='Zapamiętuje twój nick na AtCoder')
  async def set_(interaction, handle: str):
    logging.info(f'{interaction.user.id} requested to set their AtCoder handle to {handle!r}')

    if any(i not in string.ascii_letters + string.digits + '_' for i in handle):
      await interaction.response.send_message('Taki nick zawiera niedozwolone znaki… 🤨', ephemeral=True)
      return

    async with aiohttp.ClientSession() as session:
      response = await session.get(f'https://atcoder.jp/users/{handle}')
    if response.status == 404:
      await interaction.response.send_message('Nie ma na AtCoder konta o takim nicku… 🤨', ephemeral=True)
      return
    response.raise_for_status()

    a = random.choice(['Agenci', 'Legendy', 'Mistrzowie', 'Pogromcy', 'Przyjaciele', 'Zaklinacze', 'Zbawiciele', 'Zjadacze'])
    b = random.choice(['USB', 'Obozów', 'Heur', 'Krokietów', 'Gąsienic', 'Szczurów', 'Kontestów', 'Zadań'])

    # U+202F is not a word break and allows both words to be selected at once.
    await interaction.response.send_message(f'Aby zweryfikować przynależność tego konta do ciebie, [ustaw swoją przynależność](https://atcoder.jp/settings) na `{a}\u202f{b}` w ciągu **{3 * 60} sekund** i czekaj aż do upłynięcia reszty czasu. 🥺', ephemeral=True, suppress_embeds=True)
    await asyncio.sleep(3 * 60)

    async with aiohttp.ClientSession(raise_for_status=True) as session:
      text = await (await session.get(f'https://atcoder.jp/users/{handle}')).text()
    try:
      read = next(i.td.text for i in BeautifulSoup(text, 'lxml').find_all('tr') if i.th.text == 'Affiliation')
    except StopIteration:
      read = None

    if read is not None and ''.join(read.split()) == a + b:
      logging.info(f'{interaction.user.id} has successfully set their AtCoder handle to {handle!r}')
      database.data.setdefault('atcoder_handles', {})[interaction.user.id] = handle
      database.should_save = True
      await interaction.edit_original_response(content=f'Pomyślnie zweryfikowano i ustawiono twój nick na AtCoder na `{handle}`! 🥳\n')
    else:
      logging.info(f'{interaction.user.id} failed to verify their AtCoder handle ({read!r} != {a!r} & {b!r})')
      if read is None:
        read = 'end of file'
      elif '`' in read:
        read = 'stringa z grawisami (*ty hakierze*)'
      else:
        read = f'`{read}`'
      await interaction.edit_original_response(content=f'Weryfikacja nie powiodła się. Oczekiwano `{a} {b}`, wczytano {read}. 😕')

  async def get(interaction, user):
    handle = database.data.get('atcoder_handles', {}).get(user.id)
    if handle is None:
      await interaction.response.send_message(f'{user.mention} nie podzielił się jeszcze swoim nickiem na AtCoder. 🕵️', ephemeral=True)
    else:
      await interaction.response.send_message(f'{user.mention} ma nick [`{handle}`](https://atcoder.jp/users/{handle}) na AtCoder. 🕵️', ephemeral=True, suppress_embeds=True)

  @atcoder.command(name='get', description='Pokazuje nick użytkownika na AtCoder')
  async def cmd_get(interaction, user: discord.User | None):
    await get(interaction, interaction.user if user is None else user)

  @bot.tree.context_menu(name='Pokaż nick na AtCoder')
  async def menu_get(interaction, user: discord.User):
    await get(interaction, user)

  @atcoder.command(description='Zapomina twój nick na AtCoder')
  async def unset(interaction):
    try:
      del database.data['atcoder_handles'][interaction.user.id]
      database.should_save = True
    except KeyError:
      await interaction.response.send_message('Nie podałeś mi jeszcze swojego nicku na AtCoder… 🤨', ephemeral=True)
    else:
      logging.info(f'{interaction.user.id} has unset their AtCoder handle')
      await interaction.response.send_message('Pomyślnie zapomniano twój nick na AtCoder. 🫡', ephemeral=True)

async def send_standings(contest_id):
  async with aiohttp.ClientSession(raise_for_status=True) as session:
    html = BeautifulSoup(await (await session.get(f'https://atcoder.jp/contests/{contest_id}')).text(), 'lxml')
  await send_national_standings(Contest(
    contest_id,
    html.find(class_='contest-title').text.strip(),
    datetime.fromisoformat(html.find(class_='contest-duration').time.text),
  ))

console.begin('atcoder')
console.register('send_standings', '<id>', 'send the standings of Polish contestants in an AtCoder contest', lambda x: asyncio.run_coroutine_threadsafe(send_standings(x), bot.loop).result())
console.end()
