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

import logging, pprint, random, subprocess
from datetime import datetime

from common import config

def setup(bot):
  setup_time = datetime.now().astimezone()

  @bot.tree.command(name='config', description='Wyświetla konfigurację bota')
  async def _config(interaction):
    result = config.copy()
    del result['token']
    del result['youtube_api_key']
    result = pprint.pformat(result, sort_dicts=False)
    await interaction.response.send_message(f'Moja wewnętrzna konfiguracja wygląda następująco:```json\n{result}```', ephemeral=True)

  @bot.tree.command(description='Dziękuje istotnym twórcom bota')
  async def credits(interaction):
    users = [671790729676324867, 386516541790748673, 536253933778370580]
    contributors = ', '.join(f'<@{i}>' for i in users)
    await interaction.response.send_message(f'OOOZet powstał dzięki wspólnym staraniom {contributors} i innych. 🙂', ephemeral=True)

  @bot.tree.command(description='Sprawdza ping bota')
  async def ping(interaction):
    await interaction.response.send_message(f'Pong! `{1000 * bot.latency:.0f}ms`', ephemeral=True)

  @bot.tree.command(description='Sprawdza uptime serwera i bota')
  async def uptime(interaction):
    server_uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True).stdout.strip()
    bot_uptime = interaction.created_at - setup_time
    await interaction.response.send_message(
      f'''
Uptime serwera to: `{server_uptime}` 🖥️
Uptime bota to: `{bot_uptime}` 🤖
      ''',
      ephemeral=True,
    )

  @bot.tree.error
  async def error(interaction, error):
    logging.exception(f'Got exception in app command {repr(interaction.command.name)}')

    emoji = random.choice(['😖', '🫠', '😵', '😵‍💫', '🥴'])
    if config['server_maintainer'] is None:
      await interaction.response.send_message(f'Upss… Coś poszło nie tak. W dodatku nikt nie jest za to odpowiedzialny! {emoji}')
    else:
      await interaction.response.send_message(f'Upss… Coś poszło nie tak. Napisz do <@{config["server_maintainer"]}>, żeby sprawdził logi. {emoji}')
