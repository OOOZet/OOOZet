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

import discord
from dataclasses import dataclass

from common import config, hybrid_check

def is_staff(member):
  return any(member.get_role(i) is not None for i in config['staff_roles'])

@dataclass
class NotStaffError(discord.app_commands.CheckFailure):
  action: str

def check_staff(action=None): # "… uprawnień do {action}, …"
  @hybrid_check(is_consistent=True)
  def pred(interaction):
    if interaction.guild is None or interaction.guild.id != config['guild']:
      return False # Asserts don't get caught in app command checks.
    if not is_staff(interaction.user):
      raise NotStaffError(action)
  return pred

async def setup(bot):
  @bot.on_check_failure
  async def on_check_failure(interaction, error):
    if isinstance(error, NotStaffError):
      await interaction.response.send_message(f'Nie masz uprawnień do {error.action}, tylko administracja może to robić. 😡', ephemeral=True)
    else:
      raise
