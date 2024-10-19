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

import asyncio, logging
from datetime import datetime

import database
from common import config

async def setup(bot):
  lock = asyncio.Lock()

  async def clean():
    if config['counting_channel'] is None:
      return

    if 'counting_clean_until' not in database.data:
      logging.info('#counting has never been cleaned before')
      database.data['counting_clean_until'] = datetime.now().astimezone()
      database.should_save = True

    async with lock:
      async for msg in bot.get_channel(config['counting_channel']).history(limit=None, after=database.data['counting_clean_until']):
        try:
          num = int(msg.content)
        except ValueError:
          await msg.delete()
        else:
          if num == database.data.get('counting_num', num) and not msg.author.bot:
            if 'counting_num' in database.data:
              logging.info(f'{msg.author.id} has upped the counting number to {num}')
            else:
              logging.info(f'{msg.author.id} has called the initial counting number at {num}')

            database.data['counting_num'] = num + 1
            database.data['counting_clean_until'] = msg.created_at
            database.should_save = True
          else:
            await msg.delete()

  @bot.listen()
  async def on_ready():
    logging.info('Cleaning #counting')
    await clean()
    logging.info('Counting is ready')

  @bot.listen()
  async def on_message(msg):
    if msg.channel.id == config['counting_channel']:
      logging.info('Cleaning #counting after a new message')
      await clean() # on_message can come before on_ready.
