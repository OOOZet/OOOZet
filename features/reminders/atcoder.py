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
from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime, timedelta

from common import config, mention_datetime, parse_duration, sleep_until

async def setup(bot):
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
    await bot.get_channel(config['atcoder_channel']).send(f'{mention} [{contest.title}]({contest.link}) zaczyna się {relative_time}! 🔔', suppress_embeds=True)

  reminders = []

  @discord.ext.tasks.loop(seconds=parse_duration(config['atcoder_poll_rate']))
  async def poll():
    logging.info('Periodically downloading AtCoder contest schedule')

    async with aiohttp.ClientSession() as session:
      response = await session.get('https://atcoder.jp/contests/')
      response.raise_for_status()
      html = BeautifulSoup(await response.text(), 'lxml').find(id='contest-table-upcoming').tbody.find_all('tr')

    for task in reminders:
      task.cancel()
    reminders.clear()

    for entry in html:
      entry = entry.find_all('td')
      contest = Contest(
        entry[1].a['href'].removeprefix('/contests/'),
        entry[1].a.text,
        datetime.fromisoformat(entry[0].text),
      )

      if datetime.now().astimezone() < contest.time:
        reminders.append(asyncio.create_task(remind(contest)))

  poll.start()
