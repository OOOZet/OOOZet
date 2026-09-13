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

import aiohttp, asyncio, discord, logging
from dataclasses import dataclass
from datetime import datetime, timezone

import console, database
from common import config, log_exceptions, loop, mention_datetime, parse_duration
from features.codeforces_handles import get_handle

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
    return all(i not in self.title for i in ['Round', 'Hello', 'Good Bye', 'Rated'])

async def send_national_standings(contest):
  logging.info(f'Sending national standings for Codeforces contest {contest.id}')

  if config['codeforces_channel'] is None:
    return

  # Gentlemen, this is poor API design manifest!
  should_be_rated = not contest.is_niche and 'Unrated' not in contest.title
  # There is actually no proper way to check this… For unrated contests, the
  # possible replies are a proper error (e.g. contest 2181) or an empty result
  # (e.g. contest 2082). For rated contests that haven't finished yet it returns
  # a proper error, for ones that did finish but have not been assigned rating
  # changes yet it returns an empty result, and in other cases it returns
  # a proper result, or an incomplete one if you're especially lucky.
  #
  # In the past we used to detect the last case by checking, if all the
  # participants that should have a rating change did, in fact, have one. And we
  # could easily tell whether a contestant should have a rating change by
  # comparing their participantType to 'CONTESTANT'. Unfortunately, at the
  # beginning of 2026, Codeforces started marking some unrated-by-choice
  # contestants, whom it had always labeled as OUT_OF_COMPETITION up to that
  # point, as CONTESTANT. That's some real bollocks right there.

  async with aiohttp.ClientSession('https://codeforces.com/api/') as session:
    prev_json = None
    while True:
      json = await (await session.get('contest.ratingChanges', params={'contestId': contest.id})).json()
      if json == prev_json:
        break
      prev_json = json
      await asyncio.sleep(parse_duration(config['codeforces_api_lag']))

    if json['status'] != 'OK':
      if json['comment'] == 'contestId: Rating changes are unavailable for this contest':
        if should_be_rated:
          logging.warn(f'Failed to detect an unrated contest: {contest}')
          should_be_rated = False
      else:
        raise Exception(f'Rating changes request failed: {json["comment"]!r}')
    elif not json['result'] and should_be_rated:
      raise Exception('Rating changes are not available yet')
    elif json['result'] and not should_be_rated:
      logging.warn(f'Failed to detect a rated contest: {contest}')
      should_be_rated = True
    rating_changes = {i['handle']: i for i in json.get('result', [])}

    standings = await (await session.get('contest.standings', params={'contestId': contest.id})).json()
    if standings['status'] != 'OK':
      raise Exception(f'Standings request failed: {standings["comment"]!r}')
    standings = [i for i in standings['result']['rows'] if i['party']['participantType'] in {'CONTESTANT', 'OUT_OF_COMPETITION'}]

    user_infos = {}

    old_user_handles = database.data.get('codeforces_handles', {}).copy()
    handles = [member['handle'] for entry in standings for member in entry['party']['members']] + list(old_user_handles.values())
    # Codeforces's documentation says we are allowed to write in as many as 10'000
    # users but it seems like they 400 Bad Request any request with a count of at
    # least around 700 users anyways and even more worryingly some rare requests
    # with ~600 users cause a 502 Bad Gateway error.
    for i in range(0, len(handles), 500):
      batch = handles[i : i + 500]

      json = await (await session.get('user.info', params={'handles': ';'.join(batch)})).json()
      if json['status'] != 'OK':
        raise Exception(f'User info request failed: {json["comment"]!r}')

      assert len(batch) == len(json['result'])
      user_infos.update(zip(batch, json['result']))

    for user, old_handle in old_user_handles.items():
      new_handle = user_infos[old_handle]['handle']
      if new_handle == old_handle or get_handle(user) != old_handle:
        continue
      logging.info(f"Updating {user}'s Codeforces handle from {old_handle!r} to {new_handle!r}")
      set_handle(user, new_handle)

  lines = []

  reverse_handles = {v: k for k, v in database.data.get('codeforces_handles', {}).items()}
  for entry in standings:
    team = [member['handle'] for member in entry['party']['members']]

    if not all(user_infos[i].get('country') == 'Poland' for i in team):
      continue

    line = f'{len(lines) + 1}. #{entry["rank"]} ' + ', '.join(
      f'<@{reverse_handles[handle]}>' if handle in reverse_handles else f'[{handle}](https://codeforces.com/profile/{handle})'
      # contest.standings/contest.ratingChanges sometimes contains outdated handles. :rolling_eyes:
      for handle in map(lambda x: user_infos[x]['handle'], team)
    )
    if team[0] in rating_changes:
      assert len(team) == 1
      old = rating_changes[team[0]]['oldRating']
      new = rating_changes[team[0]]['newRating']
      line += f' {old} → {new}'
      delta = new - old
      if delta > 0:
        line += f' **({delta:+})**'
      else:
        line += f' ({delta:+})'
    else:
      assert all(i not in rating_changes for i in team)
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

  @log_exceptions
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

  @loop(interval=config['codeforces_contest_poll_rate'])
  async def poll():
    logging.info('Periodically downloading Codeforces contest list')

    async with aiohttp.ClientSession('https://codeforces.com/api/') as session:
      json = await (await session.get('contest.list')).json()
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
        try:
          await send_national_standings(contest)
        except:
          logging.exception('Got exception while sending Codeforces national standings')
        else:
          watchlist.remove(contest.id)

  poll.start()

async def send_standings(contest_id):
  async with aiohttp.ClientSession('https://codeforces.com/api/') as session:
    json = await (await session.get('contest.standings', params={'contestId': contest_id})).json()
  if json['status'] != 'OK':
    raise Exception(f'Codeforces contest standings request failed: {json["comment"]!r}')
  await send_national_standings(Contest.from_json(json['result']['contest']))

console.begin('codeforces')
console.register('send_standings', '<id>', 'send the standings of Polish contestants in a Codeforces contest', lambda x: asyncio.run_coroutine_threadsafe(send_standings(int(x)), bot.loop).result())
console.end()
