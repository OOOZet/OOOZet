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

  reminders = []

  @discord.ext.tasks.loop(seconds=parse_duration(config['codeforces_poll_rate']))
  async def poll():
    logging.info('Periodically downloading Codeforces contest schedule')

    response = requests.get('https://codeforces.com/api/contest.list', timeout=parse_duration(config['codeforces_timeout']))
    response.raise_for_status()
    json = response.json()
    if json['status'] != 'OK':
      logging.error(f'Codeforces contest schedule request failed: {json["comment"]!r}')
      return

    for task in reminders:
      task.cancel()
    reminders.clear()

    for entry in json['result']:
      if entry['phase'] != 'BEFORE':
        continue

      contest = Contest(
        entry['id'],
        entry['name'],
        datetime.fromtimestamp(entry['startTimeSeconds'], tz=timezone.utc),
      )

      delay = -entry['relativeTimeSeconds'] - parse_duration(config['codeforces_advance'])
      if delay > 0:
        reminders.append(asyncio.create_task(remind(contest, delay)))

  poll.start()
