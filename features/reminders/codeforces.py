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

import asyncio, discord, logging, requests
from dataclasses import dataclass
from datetime import datetime, timezone

from common import config, mention_datetime, parse_duration

def setup(bot):
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

    response = requests.get(f'https://codeforces.com/api/contest.ratingChanges?contestId={contest.id}', timeout=parse_duration(config['codeforces_timeout']))
    response.raise_for_status()
    json = response.json()
    if json['status'] != 'OK':
      if json['comment'] == 'contestId: Rating changes are unavailable for this contest':
        return
      logging.error(f'Codeforces contest rating changes request failed: {json["comment"]!r}')
      return True
    elif not json['result']:
      logging.error('Codeforces contest rating changes are not available yet')
      return True

    lines = []

    # Codeforces's documentation says we are allowed to write in as many as
    # 10'000 users but it seems like their infrastructure fails anyway for any
    # count of at least around 700 users.
    for i in range(0, len(json['result']), 600):
      batch = json['result'][i : i + 600]

      response = requests.get('https://codeforces.com/api/user.info?handles=' + ';'.join(map(lambda x: x['handle'], batch)), timeout=parse_duration(config['codeforces_timeout']))
      response.raise_for_status()
      user_infos = response.json()
      if user_infos['status'] != 'OK':
        logging.error(f'Codeforces user info request failed: {user_infos["comment"]!r}')
        return True

      assert len(batch) == len(user_infos['result'])
      for entry, user_info in zip(batch, user_infos['result']):
        if user_info.get('country') != 'Poland':
          continue
        # contest.ratingChanges sometimes contains outdated handles. :rolling_eyes:
        line = f'{len(lines) + 1}. #{entry["rank"]} [{user_info["handle"]}](https://codeforces.com/profile/{user_info["handle"]}) {entry["oldRating"]} → {entry["newRating"]}'
        delta = entry['newRating'] - entry['oldRating']
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

    response = requests.get('https://codeforces.com/api/contest.list', timeout=parse_duration(config['codeforces_timeout']))
    response.raise_for_status()
    json = response.json()
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
