# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023-2026 Karol "digitcrusher" Łacina
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

import aiohttp, discord, logging
from bs4 import BeautifulSoup
from dataclasses import dataclass
from defusedxml import ElementTree
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import database
from common import config, loop

oi_feed_url = 'https://oi.edu.pl/feed/'
oi_site_url = 'https://oi.edu.pl/'
oi_logo_url = 'https://oi.edu.pl/static/images/logo_oi.png'
oi_creator_tag = '{http://purl.org/dc/elements/1.1/}creator'

oij_site_url = 'https://oij.edu.pl/'
oij_news_url = urljoin(oij_site_url, 'news/')
oij_logo_url = urljoin(oij_site_url, 'images/logo-dark.cc2f174aa055e3d58531cbfca88a58ed3c8f306db1cc5a71ad38af9ad9cc2604.png')


@dataclass
class Announcement:
  id: str
  title: str
  url: str
  description: str
  published: str = ''
  author: str = ''
  image: str | None = None


def extract_content(html, base_url, ignored_classes=()):
  blocks = []
  for block in html.find_all(['p', 'ul'], recursive=False):
    if any(name in block.get('class', []) for name in ignored_classes):
      continue
    if block.name == 'p':
      text = block.get_text(' ', strip=True)
    else:
      items = [item.get_text(' ', strip=True) for item in block.find_all('li', recursive=False)]
      text = '\n'.join(f'• {item}' for item in items if item)
    if text:
      blocks.append(text)

  if not blocks:
    text = html.get_text(' ', strip=True)
    if text:
      blocks.append(text)

  image = html.find('img', src=True)
  return '\n\n'.join(blocks), urljoin(base_url, image['src']) if image else None


def split_description(description, limit=4096):
  chunks = []
  while description:
    if len(description) <= limit:
      chunks.append(description)
      break

    split_at = max(
      description.rfind('\n\n', 0, limit + 1),
      description.rfind('\n', 0, limit + 1),
      description.rfind(' ', 0, limit + 1),
    )
    if split_at <= 0:
      split_at = limit
    chunks.append(description[:split_at].rstrip())
    description = description[split_at:].lstrip()
  return chunks


def parse_oi_entry(item):
  url = item.findtext('link', '') or oi_site_url
  description, image = extract_content(
    BeautifulSoup(item.findtext('description', ''), 'html.parser'),
    oi_site_url,
  )
  published = item.findtext('pubDate', '')
  try:
    published = parsedate_to_datetime(published).strftime('%Y-%m-%d')
  except (TypeError, ValueError):
    pass

  return Announcement(
    id=item.findtext('guid', '') or url,
    title=item.findtext('title', 'Nowe ogłoszenie OI'),
    url=url,
    description=description,
    published=published,
    author=item.findtext(oi_creator_tag, ''),
    image=image,
  )


def parse_oij_article(article):
  heading = article.find(['h2', 'h3'])
  title_link = heading.find_parent('a', href=True) if heading else None
  title = heading.get_text(' ', strip=True) if heading else ''
  if title_link is None or not title:
    return None

  published = article.find('time')
  description, image = extract_content(article, oij_site_url, ignored_classes=('article-metadata',))
  return Announcement(
    id=article['id'],
    title=title,
    url=urljoin(oij_news_url, title_link['href']),
    description=description,
    published=published.get('datetime', '') if published else '',
    image=image,
  )


async def setup(bot):
  async def send_announcement(announcement, channel_id, role_id, label, site_url, logo_url):
    await bot.wait_until_ready()
    channel = bot.get_channel(channel_id)
    if channel is None:
      raise RuntimeError(f'Could not find channel {channel_id} for {label} announcements')

    chunks = split_description(announcement.description) or ['Pełna treść jest dostępna pod podanym linkiem.']
    mention = f'<@&{role_id}>' if role_id is not None else ''
    allowed_mentions = discord.AllowedMentions(everyone=False, users=False, roles=True)

    for index, chunk in enumerate(chunks):
      embed = discord.Embed(
        title=announcement.title if index == 0 else f'{announcement.title} — ciąg dalszy',
        url=announcement.url,
        description=chunk,
      )
      if index == 0:
        embed.set_author(name=f'Nowe ogłoszenie {label}', url=site_url, icon_url=logo_url)
        if announcement.image:
          embed.set_image(url=announcement.image)

      footer = [label]
      if announcement.published:
        footer.append(announcement.published)
      if announcement.author:
        footer.append(announcement.author)
      if len(chunks) > 1:
        footer.append(f'{index + 1}/{len(chunks)}')
      embed.set_footer(text=' • '.join(footer))

      await channel.send(
        mention if index == 0 else '',
        embed=embed,
        allowed_mentions=allowed_mentions,
      )

  @loop(interval=config['oi_poll_rate'])
  async def poll_oi():
    logging.info('Pobieranie ogłoszeń OI')
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}, raise_for_status=True) as session:
      content = await (await session.get(oi_feed_url)).read()

    root = ElementTree.fromstring(content)
    announcements = [parse_oi_entry(item) for item in root.findall('./channel/item')]

    if 'oi_announcements' not in database.data:
      with database.lock:
        database.data['oi_announcements'] = {announcement.id for announcement in announcements}
        database.should_save = True
      logging.info(f'Initialized OI announcements with {len(announcements)} existing entries')
      return

    sent = database.data['oi_announcements']
    for announcement in reversed(announcements):
      if announcement.id in sent:
        continue
      if config['oi_channel'] is None:
        return
      await send_announcement(
        announcement, config['oi_channel'], config['oi_role'],
        'OI', oi_site_url, oi_logo_url,
      )
      with database.lock:
        sent.add(announcement.id)
        database.should_save = True

  @loop(interval=config['oij_poll_rate'])
  async def poll_oij():
    logging.info('Pobieranie ogłoszeń OIJ')
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}, raise_for_status=True) as session:
      text = await (await session.get(oij_news_url)).text()

    html = BeautifulSoup(text, 'html.parser')
    announcements = [
      announcement
      for article in html.find_all('article', id=lambda id: id and id.startswith('article-'))
      if (announcement := parse_oij_article(article)) is not None
    ]

    if 'oij_announcements' not in database.data:
      with database.lock:
        database.data['oij_announcements'] = {announcement.id for announcement in announcements}
        database.should_save = True
      logging.info(f'Initialized OIJ announcements with {len(announcements)} existing entries')
      return

    sent = database.data['oij_announcements']
    for announcement in reversed(announcements):
      if announcement.id in sent:
        continue
      if config['oij_channel'] is None:
        return
      await send_announcement(
        announcement, config['oij_channel'], config['oij_role'],
        'OIJ', oij_site_url, oij_logo_url,
      )
      with database.lock:
        sent.add(announcement.id)
        database.should_save = True

  poll_oi.start()
  poll_oij.start()
