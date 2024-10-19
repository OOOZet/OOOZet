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

import asyncio, discord, logging, os, re, requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from urllib.parse import unquote, urlparse

import database
from common import config, parse_duration

def find_problem(url):
  url = urlparse(unquote(url))
  path = os.path.normpath(url.path).replace('//', '/')

  if url.hostname == 'codeforces.com':
    if (match := re.fullmatch('/(?:contest|gym)/([0-9]+)/problem/([A-Za-z0-9]+)', path)) or \
       (match := re.fullmatch('/problemset/problem/([0-9]+)/([A-Za-z0-9]+)', path)):
      contest = int(match[1])
      letter = match[2].upper()
      response = requests.get(f'https://codeforces.com/api/contest.standings?contestId={contest}&count=1', timeout=parse_duration(config['codeforces_timeout']))
      response.raise_for_status()
      return (
        'https://codeforces.com/' + ('contest' if contest <= 100000 else 'gym') + f'/{contest}/problem/{letter}',
        next(i['name'] for i in response.json()['result']['problems'] if i['index'] == letter),
      )

    elif match := re.match('/(?:contest|gym)/([0-9]+)', path):
      contest = int(match[1])
      response = requests.get(f'https://codeforces.com/api/contest.standings?contestId={contest}&count=1', timeout=parse_duration(config['codeforces_timeout']))
      response.raise_for_status()
      return (
        'https://codeforces.com/' + ('contest' if contest <= 100000 else 'gym') + f'/{contest}',
        response.json()['result']['contest']['name'],
      )

  elif url.hostname == 'atcoder.jp':
    if match := re.match('/contests/([^/]+)/tasks/([^/]+)', path):
      url = f'https://atcoder.jp/contests/{match[1].lower()}/tasks/{match[2].lower()}'
      response = requests.get(url, timeout=parse_duration(config['atcoder_timeout']))
      response.raise_for_status()
      return url, BeautifulSoup(response.text, 'lxml').head.title.text.partition(' - ')[2]

    elif match := re.match('/contests/([^/]+)', path):
      url = f'https://atcoder.jp/contests/{match[1].lower()}'
      response = requests.get(url, timeout=parse_duration(config['atcoder_timeout']))
      response.raise_for_status()
      return url, BeautifulSoup(response.text, 'lxml').find(class_='contest-title').text

  elif url.hostname == 'szkopul.edu.pl':
    if match := re.match('/problemset/problem/([^/]+)/site', path):
      url = f'https://szkopul.edu.pl/problemset/problem/{match[1]}/site'
      response = requests.get(url, timeout=parse_duration(config['szkopul_timeout']))
      response.raise_for_status()
      return url, BeautifulSoup(response.text, 'lxml').find(class_='problem-title').h1.text.rpartition(' (')[0]

  elif url.hostname == 'oj.uz':
    if match := re.match('/problem/[a-z]+/([^/]+)', path):
      url = f'https://oj.uz/problem/view/{match[1]}'
      response = requests.get(url, timeout=parse_duration(config['ojuz_timeout']))
      response.raise_for_status()
      soup = BeautifulSoup(response.text, 'lxml')
      return (
        'https://oj.uz' + soup.find(lambda x: x.name == 'a' and x.text == 'Statement')['href'],
        next(soup.find(class_='problem-title').h1.strings).strip(),
      )

def setup(bot):
  lock = asyncio.Lock()

  async def clean():
    if config['fajne_zadanka_channel'] is None:
      return

    if 'fajne_zadanka_clean_until' not in database.data:
      logging.info('#fajne-zadanka has never been cleaned before')
      database.data['fajne_zadanka_clean_until'] = datetime.now().astimezone()
      database.should_save = True

    async with lock:
      async for msg in bot.get_channel(config['fajne_zadanka_channel']).history(limit=None, after=database.data['fajne_zadanka_clean_until']):
        if msg.author == bot.user:
          continue

        await msg.delete()
        if msg.author.bot:
          continue

        if match := re.match('https?://[^\s]+', msg.content):
          url = match[0]
          description = msg.content.removeprefix(url).lstrip()
        elif match := re.search('https?://[^\s]+$', msg.content):
          url = match[0]
          description = msg.content.removesuffix(url).rstrip()
        else:
          await msg.author.send(
            f'Twoja wiadomość musi zaczynać się lub konczyć linkiem do zadania, abyś mógł ją wysłać na {msg.channel.mention}. 🤓',
            file=discord.File(StringIO(msg.content), 'message.md'),
          )
          continue

        try:
          url, title = find_problem(url) or (url, url)
        except:
          logging.exception('Got exception while finding problem metadata')
          title = url

        embed = discord.Embed(title=title, url=url, description=description)
        embed.set_footer(text=msg.author.our_name, icon_url=msg.author.display_avatar.url)
        my_msg = await msg.channel.send(embed=embed)
        await my_msg.add_reaction('❤️')
        await my_msg.add_reaction('👍')
        await msg.author.send(f'Zareaguj ❌ na [swoją wiadomość]({my_msg.jump_url}), gdy będziesz chciał ją usunąć. 😊')

        database.data['fajne_zadanka_clean_until'] = msg.created_at
        database.should_save = True

  @bot.listen()
  async def on_ready():
    logging.info('Cleaning #fajne-zadanka')
    await clean()
    logging.info('Fajne zadanka is ready')

  @bot.listen()
  async def on_message(msg):
    if msg.channel.id == config['fajne_zadanka_channel']:
      logging.info('Cleaning #fajne-zadanka after a new message')
      await clean() # Same pattern as in counting.py

  @bot.listen()
  async def on_raw_reaction_add(payload):
    if payload.channel_id != config['fajne_zadanka_channel']:
      return
    msg = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
    if msg.author != bot.user or not msg.embeds:
      return

    if payload.emoji.name == '❌' and msg.embeds[0].footer.text == bot.get_user(payload.user_id).our_name: # Watch out for identity theft!
      await msg.delete()
    elif payload.emoji.name not in (i.emoji for i in msg.reactions if i.me):
      await msg.remove_reaction(payload.emoji, discord.Object(payload.user_id))
