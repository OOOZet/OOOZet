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
from defusedxml import ElementTree

import database
from common import config, mention_datetime, parse_duration
from features import websub

def setup(bot):
  @dataclass
  class YouTubeVideo:
    id: str
    title: str
    time: datetime
    is_livestream: bool

    @property
    def link(self):
      return f'https://www.youtube.com/watch?v={self.id}'

  async def remind_oki(video):
    if video.is_livestream:
      delay = (video.time - datetime.now().astimezone()).total_seconds()
      if delay < 0:
        return
      logging.info(f'Setting reminder for YouTube livestream {video.id} for {video.time}')
      await asyncio.sleep(delay)
      logging.info(f'Reminding about YouTube livestream {video.id}')

    if config['oki_channel'] is None:
      return

    mention = f'<@&{config["oki_role"]}>' if config['oki_role'] is not None else ''
    if video.is_livestream:
      announcement = f'{mention} Na kanale OKI właśnie zaczyna się transmisja na żywo: [{video.title}]({video.link})! 🔔'
    else:
      announcement = f'{mention} Na kanale OKI został opublikowany nowy film: [{video.title}]({video.link})! 🔔'
    await bot.get_channel(config['oki_channel']).send(announcement)

  def parse_youtube_feed(content):
    ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
    videos = [
      YouTubeVideo(
        i.find('yt:videoId', ns).text,
        i.find('atom:title', ns).text,
        datetime.fromisoformat(i.find('atom:published', ns).text),
        False,
      )
      for i in ElementTree.fromstring(content).findall('atom:entry', ns)
    ]

    response = requests.get(
      f'https://youtube.googleapis.com/youtube/v3/videos?key={config["youtube_api_key"]}&part=liveStreamingDetails' + ''.join(f'&id={i.id}' for i in videos),
      timeout=parse_duration(config['youtube_timeout']),
    )
    if not response.ok:
      logging.error(f'YouTube API request failed with {response.status_code}: {repr(response.text)}')
      return
    json = response.json()

    to_remove = []
    for i, video in enumerate(videos):
      if 'liveStreamingDetails' in json['items'][i]:
        try:
          video.time = datetime.fromisoformat(json['items'][i]['liveStreamingDetails']['scheduledStartTime'])
          video.is_livestream = True
        except KeyError:
          to_remove.append(video)
    for video in to_remove:
      videos.remove(video)

    return videos

  def process_youtube_feed(content):
    if 'oki_last_published' not in database.data:
      logging.info("OKI's YouTube channel has never been checked before")
      database.data['oki_last_published'] = datetime.now().astimezone()
      database.should_save = True

    last_published = database.data['oki_last_published']
    for video in parse_youtube_feed(content):
      if video.is_livestream and video.time > datetime.now().astimezone():
        asyncio.run_coroutine_threadsafe(remind_oki(video), bot.loop)
      elif not video.is_livestream and video.time > last_published:
        asyncio.run_coroutine_threadsafe(remind_oki(video), bot.loop)
        with database.lock:
          database.data['oki_last_published'] = max(database.data['oki_last_published'], video.time)
          database.should_save = True

  @bot.listen()
  async def on_ready():
    logging.info("Downloading OKI's YouTube channel feed")
    response = requests.get(
      f'https://www.youtube.com/feeds/videos.xml?channel_id={config["oki_youtube"]}',
      timeout=parse_duration(config['youtube_timeout']),
    )
    response.raise_for_status()
    process_youtube_feed(response.text)
    logging.info("Processed OKI's YouTube channel feed")

  websub.on_msg = process_youtube_feed

  @dataclass
  class CodeforcesContest:
    id: int
    title: str
    time: datetime
    duration: float

    @property
    def link(self):
      return f'https://codeforces.com/contest/{self.id}'

    @property
    def is_niche(self):
      return all(i not in self.title for i in ['Div. 1', 'Div. 2', 'Div. 3', 'Div. 4'])

  async def remind_codeforces(contest, delay=0):
    if delay > 0:
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
    await bot.get_channel(config['codeforces_channel']).send(f'{mention} [{contest.title}]({contest.link}) zaczyna się {relative_time}! 🔔', suppress_embeds=True)

  codeforces_reminders = []

  @discord.ext.tasks.loop(seconds=parse_duration(config['codeforces_poll_rate']))
  async def poll_codeforces():
    logging.info('Periodically downloading Codeforces contest schedule')

    response = requests.get('https://codeforces.com/api/contest.list', timeout=parse_duration(config['codeforces_timeout']))
    response.raise_for_status()
    json = response.json()
    if json['status'] != 'OK':
      logging.error(f'Codeforces contest schedule request failed: {repr(json["comment"])}')
      return

    for task in codeforces_reminders:
      task.cancel()
    codeforces_reminders.clear()

    for entry in json['result']:
      if entry['phase'] != 'BEFORE':
        continue

      contest = CodeforcesContest(
        entry['id'],
        entry['name'],
        datetime.fromtimestamp(entry['startTimeSeconds'], tz=timezone.utc),
        entry['durationSeconds'],
      )

      delay = -entry['relativeTimeSeconds'] - parse_duration(config['codeforces_advance'])
      if delay > 0:
        codeforces_reminders.append(asyncio.create_task(remind_codeforces(contest, delay)))

  poll_codeforces.start()
