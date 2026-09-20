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

# TODO: anti-nuke
# TODO: message server maintainer when an error happens

import asyncio, discord, random, sys, threading
from discord import app_commands
from logging import getLogger

import console
from common import config, log_exceptions, Loop, options

log = getLogger(__name__)

class Client(discord.Client):
  def __init__(self):
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())

    self.tree = app_commands.CommandTree(self)
    self.event_listeners = {}
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

    self.features = []
    for name, mod in sys.modules.items():
      if not name.startswith('features.'):
        continue
      if mod.__spec__.origin is None:
        log.debug(f'Skipping namespace module {name!r}')
        continue
      self.features.append(mod)

      assert not hasattr(mod, 'bot'), mod
      mod.bot = self
      if not hasattr(mod, 'feature_id'):
        mod.feature_id = mod.__name__.removeprefix('features.')
      if not hasattr(mod, 'log'):
        mod.log = getLogger(mod.feature_id)

    if self.features:
      log.info(f'Found imported features: {sorted(i.feature_id for i in self.features)}')
    else:
      log.warning('No imported features have been found')

  async def handle_error(self, interaction, error, log_msg):
    if isinstance(error, app_commands.CheckFailure):
      for handler in self.check_failure_handlers:
        try:
          await handler(interaction, error)
          return
        except Exception as new_error:
          if new_error is not error:
            log.exception(f'Got exception in check failure handler from {handler.__module__!r}')

    log.exception(log_msg)

    send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    emoji = random.choice(['😖', '🫠', '😵', '😵‍💫', '🥴'])
    if config['server_maintainer'] is None:
      await send(f'Upss… Coś poszło nie tak. W dodatku nikt nie jest za to odpowiedzialny! {emoji}', ephemeral=True)
    else:
      await send(f'Upss… Coś poszło nie tak. Napisz do <@{config["server_maintainer"]}>, żeby sprawdził logi. {emoji}', ephemeral=True, allowed_mentions=discord.AllowedMentions.all())

  async def setup_hook(self):
    console.async_loop = self.loop

    setup_hooks = []

    for feature in self.features:
      for name, value in vars(feature).items():
        if isinstance(value, app_commands.Group):
          self.tree.add_command(value)

        elif isinstance(value, app_commands.Command):
          if value.parent is None:
            self.tree.add_command(value)

        elif isinstance(value, app_commands.ContextMenu):
          self.tree.add_command(value)

        elif isinstance(value, console.Operation):
          if value.scope is None:
            value.scope = feature.feature_id.replace('_', '-')
          console.register(value)

        elif isinstance(value, Loop):
          value.start()

        elif callable(value) and getattr(value, '_is_event_listener', False):
          event = value.__name__
          if event == 'on_setup':
            setup_hooks.append(value)
          elif event == 'on_check_failure':
            self.check_failure_handlers.append(value)
          else:
            self.event_listeners.setdefault(event, []).append(value)

    for hook in setup_hooks:
      await hook()

    if not options['dev']:
      log.info('Syncing command tree')
      await self.tree.sync()
      await self.tree.sync(guild=discord.Object(config['guild']))

  def dispatch(self, event, *args, **kwargs):
    super().dispatch(event, *args, **kwargs)
    for listener in self.event_listeners.get(f'on_{event}', []):
      asyncio.create_task(log_exceptions(listener)(*args, **kwargs))

  async def on_ready(self):
    log.info(f'Logged in as {str(self.user)!r}')

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

@console.operation(scope='bot', desc='starts the bot')
def start():
  if start_event.is_set():
    raise Exception('The bot is already started')
  log.info('Starting bot')
  start_event.set()

@console.operation(scope='bot', desc='stops the bot')
def stop():
  if stop_event.is_set():
    raise Exception('The bot is already stopped')
  log.info('Stopping bot')
  stop_event.set()
  asyncio.run_coroutine_threadsafe(client.close(), client.loop)

console.register(start, stop)
