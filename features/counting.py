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

import asyncio, discord, logging
from datetime import datetime

import console, database
from common import config

def setup(client, tree):
  lock = asyncio.Lock()

  async def clean():
    if config['counting_channel'] is None:
      return

    if 'counting_clean_until' not in database.data:
      database.data['counting_clean_until'] = datetime.now().astimezone().isoformat()
      database.should_save = True
      return

    async with lock:
      clean_until = datetime.fromisoformat(database.data['counting_clean_until'])
      async for msg in client.get_channel(config['counting_channel']).history(limit=None, after=clean_until):
        try:
          num = int(msg.content)
        except ValueError:
          await msg.delete()
        else:
          if 'counting_num' not in database.data or num == database.data['counting_num']:
            if 'counting_num' not in database.data:
              logging.info(f'The initial counting number has been called at {num}')
            database.data['counting_num'] = num + 1
            database.data['counting_clean_until'] = msg.created_at.isoformat()
            database.should_save = True
          else:
            await msg.delete()

  @client.event
  async def on_ready():
    await clean()

  @client.event
  async def on_message(msg):
    if config['counting_channel'] is not None and msg.channel.id == config['counting_channel']:
      await clean() # on_message can come before on_ready.
