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

import discord, json, subprocess
from datetime import datetime
from io import StringIO

from common import redacted_config

async def setup(bot):
  setup_time = datetime.now().astimezone()

  @bot.tree.command(description='Wyświetla konfigurację bota')
  async def config(interaction):
    result = json.dumps(redacted_config(), indent=2)
    await interaction.response.send_message(
      'Załączam moją wewnętrzną konfigurację. 😉',
      file=discord.File(StringIO(result), 'config.json'),
      ephemeral=True,
    )

  @bot.tree.command(description='Dziękuje istotnym twórcom bota')
  async def credits(interaction):
    ids = [671790729676324867, 386516541790748673, 536253933778370580]
    contributors = ', '.join(f'<@{i}>' for i in ids)
    await interaction.response.send_message(
      f'OOOZet powstał dzięki wspólnym staraniom {contributors} i innych. [Ty też możesz znaleźć się wśród tego nielicznego grona!](https://github.com/OOOZet/OOOZet) 🙂',
      ephemeral=True, suppress_embeds=True,
    )

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
