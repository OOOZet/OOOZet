# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2026 semkishow
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

import discord
from discord import app_commands

def _miau_hash(val: str):
  EXP = 443
  MOD = 694202137
  hash = 0
  for c in val:
    hash = (hash * EXP + ord(c)) % MOD
  return hash

def _prepare_input(val: str):
  return val.lower().strip()

def _compute_love(a: str, b: str):
  return (_miau_hash(_prepare_input(a)) ^ _miau_hash(_prepare_input(b))) % 101

@app_commands.command(description='Wyświetla kompatybilność dwóch nazw')
async def love(interaction, a: str, b: str):
  embed = discord.Embed(title=f'{a} & {b}', colour=discord.Colour.red())
  embed.add_field(name='Kompatybilność:', value=f'{_compute_love(a, b)}%')
  await interaction.response.send_message(embed=embed)
