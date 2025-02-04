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

import asyncio, discord, discord.ext.commands, logging, random, threading

import console
from common import config, options
from features import about_me, counting, fajne_zadanka, help_forum, misc, rules, sugestie, utils, warns, xp
from features.reminders import atcoder, codeforces, youtube

class Client(discord.ext.commands.Bot):
  async def setup_hook(self):
    await about_me.setup(self)
    await atcoder.setup(self)
    await codeforces.setup(self)
    await counting.setup(self)
    await fajne_zadanka.setup(self)
    await help_forum.setup(self)
    await misc.setup(self)
    await rules.setup(self)
    await sugestie.setup(self)
    await utils.setup(self)
    await warns.setup(self)
    await xp.setup(self)
    await youtube.setup(self)

    if not options['debug']:
      await self.tree.sync()
      await self.tree.sync(guild=discord.Object(config['guild']))

  def __init__(self):
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    super().__init__('This parameter is irrelevant for us but we still have to put something here.', intents=intents, allowed_mentions=discord.AllowedMentions.none())

    self.check_failure_handlers = []

    @self.tree.error
    async def on_tree_error(interaction, error):
      await self.handle_error(interaction, error, f'Got exception in app command {interaction.command.name!r}')
    bot = self
    async def on_view_error(self, interaction, error, item):
      await bot.handle_error(interaction, error, f'Got exception in view {self!r} for item {item!r}')
    async def on_modal_error(self, interaction, error):
      await bot.handle_error(interaction, error, f'Got exception in modal {self!r}')
    discord.ui.View.on_error = on_view_error
    discord.ui.Modal.on_error = on_modal_error

  def on_check_failure(self, handler):
    self.check_failure_handlers.append(handler)

  async def handle_error(self, interaction, error, log_msg):
    if isinstance(error, discord.app_commands.CheckFailure):
      for handler in self.check_failure_handlers:
        try:
          await handler(interaction, error)
          return
        except Exception as new_error:
          if new_error is not error:
            logging.exception(f'Got exception in check failure handler from {handler.__module__!r}')

    logging.exception(log_msg)

    send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    emoji = random.choice(['😖', '🫠', '😵', '😵‍💫', '🥴'])
    if config['server_maintainer'] is None:
      await send(f'Upss… Coś poszło nie tak. W dodatku nikt nie jest za to odpowiedzialny! {emoji}', ephemeral=True)
    else:
      await send(f'Upss… Coś poszło nie tak. Napisz do <@{config["server_maintainer"]}>, żeby sprawdził logi. {emoji}', ephemeral=True, allowed_mentions=discord.AllowedMentions.all())

  async def on_ready(self):
    logging.info(f'Logged in as {str(self.user)!r}')

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
