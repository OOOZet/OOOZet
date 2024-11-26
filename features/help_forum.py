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

import asyncio, discord, logging
from datetime import datetime, timedelta

import console, database
from common import config, parse_duration

bot = None

async def setup(_bot):
  global bot
  bot = _bot

  @bot.listen()
  async def on_message(msg):
    if msg.id == msg.channel.id and msg.channel.parent_id == config['help_forum_channel'] and config['help_forum_ping_channel'] is not None:
      mention = f'<@&{config["help_forum_ping_role"]}>' if config['help_forum_ping_role'] is not None else ''
      await bot.get_channel(config['help_forum_ping_channel']).send(f'{mention} Ktoś potrzebuje pomocy na {msg.channel.mention}! 🆘')

  def get_ranking():
    return sorted(database.data.get('help_forum_karma', {}).items(), key=lambda x: x[1], reverse=True)

  @bot.tree.command(description='Wyświetla 10 najbardziej pomocnych użytkowników w ostatnim czasie')
  async def helpful(interaction):
    ranking = get_ranking()
    assert ranking

    result = 'Ranking 10 najbardziej pomocnych użytkowników w ostatnim czasie: ❤️\n'
    for i, entry in enumerate(ranking[:10]):
      result += f'{i + 1}. <@{entry[0]}> z **{entry[1]:.2f}** rozwiązanymi pytaniami\n'
    await interaction.response.send_message(result, ephemeral=True)

  @discord.ext.tasks.loop(seconds=parse_duration(config['help_forum_eval_rate']))
  async def eval():
    await bot.wait_until_ready()
    if config['help_forum_channel'] is None:
      return

    logging.info('Periodically evaluating help forum karma')

    now = datetime.now().astimezone()
    eval_max_age = parse_duration(config['help_forum_eval_max_age']) if config['help_forum_eval_max_age'] is not None else None
    contrib_cooldown = parse_duration(config['help_forum_contrib_cooldown'])
    async def eval_post(post, is_archived):
      if eval_max_age is not None and post.created_at + timedelta(seconds=eval_max_age) < now:
        return

      try:
        last_update = post.archive_timestamp if is_archived else (await anext(post.history(limit=1))).created_at
      except StopAsyncIteration:
        last_update = now
      if post.id not in database.data.setdefault('help_forum_posts', {}) or database.data['help_forum_posts'][post.id]['last_eval'] < last_update:
        contribs = {}
        last_contrib = {}
        async for msg in post.history(limit=None, oldest_first=True):
          user = msg.author.id
          if user == post.owner_id or msg.author.bot or (user in last_contrib and (msg.created_at - last_contrib[user]).total_seconds() < contrib_cooldown):
            continue
          try:
            contribs[user] += 1
          except KeyError:
            contribs[user] = 1
          last_contrib[user] = msg.created_at
        database.data['help_forum_posts'][post.id] = {
          'contribs': contribs,
          'last_eval': now,
        }

      contribs = database.data['help_forum_posts'][post.id]['contribs']
      total = sum(contribs.values())
      for user, contrib in contribs.items():
        contrib /= total
        try:
          database.data['help_forum_karma'][user] += contrib
        except KeyError:
          database.data['help_forum_karma'][user] = contrib

    database.data['help_forum_karma'] = {}
    forum = bot.get_channel(config['help_forum_channel'])
    for post in forum.threads:
      await eval_post(post, False)
    async for post in forum.archived_threads(limit=None):
      await eval_post(post, True)
    database.should_save = True

    for member in bot.get_guild(config['guild']).get_role(config['help_forum_award_role']).members:
      await member.remove_roles(discord.Object(config['help_forum_award_role']))

    awardedc = 0
    for user, _ in get_ranking():
      if awardedc >= config['help_forum_award_count']:
        break
      member = bot.get_guild(config['guild']).get_member(user)
      if member is not None:
        await member.add_roles(discord.Object(config['help_forum_award_role']))
        awardedc += 1

  eval.start()
