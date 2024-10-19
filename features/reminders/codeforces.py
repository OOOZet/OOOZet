# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023-2024 Karol "digitcrusher" Łacina
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

import aiohttp, asyncio, discord, logging
from dataclasses import dataclass
from datetime import datetime, timezone

from common import config, mention_datetime, parse_duration

async def setup(bot):
  @dataclass
  class Contest:
    id: int
    title: str
    time: datetime

    @property
    def link(self):
      return f'https://codeforces.com/contest/{self.id}'

    @property
    def is_niche(self):
      return all(i not in self.title for i in ['Div. 1', 'Div. 2', 'Div. 3', 'Div. 4', 'Hello', 'Good Bye', 'Global'])

  async def remind(contest, delay=0):
    if delay > 0:
      logging.info(f'Setting reminder for Codeforces contest {contest.id} for {delay} seconds')
      await asyncio.sleep(delay)
      logging.info(f'Reminding about Codeforces contest {contest.id}')

    if config['codeforces_channel'] is None:
      return

    if not contest.is_niche and config['codeforces_role'] is not None:
      mention = f'<@&{config["codeforces_role"]}>' # TODO: seperate roles for div1, div2 etc
    else:
      mention = ''
    relative_time = mention_datetime(contest.time, relative=True)
    await bot.get_channel(config['codeforces_channel']).send(f'{mention} [{contest.title}]({contest.link}) zaczyna się {relative_time}! 🔔', suppress_embeds=True)

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

    for entry in standings['result']['rows']:
      team = [member['handle'] for member in entry['party']['members']]

      if not all(user_infos[i].get('country') == 'Poland' for i in team):
        continue

      line = f'{len(lines) + 1}. #{entry["rank"]} '
      # contest.standings/contest.ratingChanges sometimes contains outdated handles. :rolling_eyes:
      line += ', '.join(f'[{user_infos[i]["handle"]}](https://codeforces.com/profile/{user_infos[i]["handle"]})' for i in team)
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
      contest = Contest(
        entry['id'],
        entry['name'],
        datetime.fromtimestamp(entry['startTimeSeconds'], tz=timezone.utc),
      )

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
