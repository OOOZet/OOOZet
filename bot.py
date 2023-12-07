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

import asyncio, discord, discord.ext.commands, logging, threading

import console
from common import config
from features import about_me, counting, misc, sugestie, warns, xp

class Client(discord.ext.commands.Bot):
  async def setup_hook(self):
    about_me.setup(self)
    counting.setup(self)
    misc.setup(self)
    sugestie.setup(self)
    warns.setup(self)
    xp.setup(self)
    await self.tree.sync()

  def __init__(self):
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    super().__init__('This parameter is irrelevant for us but we still have to put something here.', intents=intents)

  async def on_ready(self):
    logging.info(f'Logged in as {repr(str(self.user))}')

# TODO: aktualizowanie regulaminu
# TODO: egzekwowanie regulaminu

client = None
start_event = threading.Event()
stop_event = threading.Event()

def run():
  start()
  try:
    while True:
      start_event.wait()
      stop_event.clear()

      global client
      client = Client()
      asyncio.run(client.start(config['token'])) # The Client object is useless after this.
      client = None

      start_event.clear()
      if not stop_event.is_set():
        break
  except KeyboardInterrupt:
    pass

def start():
  if start_event.is_set():
    raise Exception('The bot is already started')
  logging.info('Starting bot')
  start_event.set()

def stop():
  if stop_event.is_set():
    raise Exception('The bot is already stopped')
  logging.info('Stopping bot')
  stop_event.set()
  asyncio.run_coroutine_threadsafe(client.close(), client.loop)

console.begin('bot')
console.register('start', None, 'starts the bot', start)
console.register('stop',  None, 'stops the bot',  stop)
console.end()
