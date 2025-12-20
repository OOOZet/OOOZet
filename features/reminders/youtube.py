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

import aiohttp, asyncio, discord, emoji, logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from defusedxml import ElementTree
from itertools import groupby

import database
from common import config, mention_datetime, parse_duration, sleep_until
from features.reminders import websub

async def setup(bot):
  @dataclass
  class Video:
    id: str
    title: str
    time: datetime
    is_livestream: bool

    @property
    def link(self):
      return f'https://www.youtube.com/watch?v={self.id}'

    @property
    def emojiless_title(self):
      return ' '.join(
        ''.join(token.value for token in group).strip()
        for is_not_emoji, group in groupby(emoji.analyze(self.title, non_emoji=True), lambda token: isinstance(token.value, str))
        if is_not_emoji
      )

  async def remind(video):
    if video.is_livestream:
      time = video.time - timedelta(seconds=parse_duration(config['youtube_advance']))
      logging.info(f'Setting reminder for YouTube livestream {video.id} for {time}')
      await sleep_until(time)
      logging.info(f'Reminding about YouTube livestream {video.id}')

    if config['oki_channel'] is None:
      return

    mention = f'<@&{config["oki_role"]}>' if config['oki_role'] is not None else ''
    if video.is_livestream:
      relative_time = mention_datetime(video.time, relative=True)
      announcement = f'{mention} {relative_time} na kanale OKI zaczyna się transmisja na żywo: [{video.emojiless_title}]({video.link})! 🔔'
    else:
      announcement = f'{mention} Na kanale OKI został opublikowany nowy film: [{video.emojiless_title}]({video.link})! 🔔'
    await bot.wait_until_ready()
    await bot.get_channel(config['oki_channel']).send(announcement, allowed_mentions=discord.AllowedMentions.all())

  reminders = {}

  async def process_videos(ids):
    async with aiohttp.ClientSession() as session:
      response = await session.get(f'https://youtube.googleapis.com/youtube/v3/videos?key={config["youtube_api_key"]}&part=snippet,liveStreamingDetails' + ''.join(f'&id={i}' for i in ids))
      if not response.ok:
        logging.error(f'YouTube API request failed with {response.status}: {await response.text()!r}')
        return
      json = await response.json()

    videos = []
    for entry in json['items']:
      video = Video(entry['id'], entry['snippet']['title'], datetime.fromisoformat(entry['snippet']['publishedAt']), False)
      if 'liveStreamingDetails' in entry:
        try:
          video.time = datetime.fromisoformat(entry['liveStreamingDetails']['scheduledStartTime'])
          video.is_livestream = True
        except KeyError:
          continue
      videos.append(video)

    if 'oki_last_published' not in database.data:
      logging.info("OKI's YouTube channel has never been checked before")
      database.data['oki_last_published'] = datetime.now().astimezone()
      database.should_save = True

    last_published = database.data['oki_last_published']
    for video in videos:
      if video.time <= (datetime.now().astimezone() - timedelta(seconds=parse_duration(config['youtube_advance'])) if video.is_livestream else last_published):
        continue

      try:
        reminders[video.id].cancel()
      except KeyError:
        pass
      reminders[video.id] = asyncio.create_task(remind(video))

      if not video.is_livestream:
        with database.lock:
          database.data['oki_last_published'] = max(database.data['oki_last_published'], video.time)
          database.should_save = True

  async def process_feed(content):
    ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
    await process_videos(i.find('yt:videoId', ns).text for i in ElementTree.fromstring(content).findall('atom:entry', ns))

  websub.on_msg = lambda feed: asyncio.run_coroutine_threadsafe(process_feed(feed), bot.loop)

  try:
    logging.info("Downloading OKI's YouTube channel feed")
    async with aiohttp.ClientSession() as session:
      response = await session.get(f'https://youtube.googleapis.com/youtube/v3/search?channelId={config["oki_youtube"]}&type=video&order=date&maxResults=50&key={config["youtube_api_key"]}')
      if not response.ok:
        logging.error(f'YouTube API request failed with {response.status}: {await response.text()!r}')
        return
      await process_videos(i['id']['videoId'] for i in (await response.json())['items'])
    logging.info("Processed OKI's YouTube channel feed")
  except Exception as e:
    logging.exception('Got exception while downloading YouTube channel feed')
