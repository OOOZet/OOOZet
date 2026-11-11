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

import asyncio
from discord import app_commands

import database
from common import config, event_listener, parse_duration
from features.utils import check_staff

# This is more accurate, than TextChannel.last_message_id for some reason, so we just use it.
async def _get_last_message(channel):
  async for message in channel.history(limit=1):
    return message

async def _remove_last_sticky(channel):
  message_id = database.data.get('sticky_messages', {}).get(channel.id, {}).get('message_id', None)
  if message_id is None:
    return
  message = await channel.fetch_message(message_id)
  await message.delete()

@event_listener
async def on_message(message):
  sticky_active = database.data.get('sticky_messages', {}).get(message.channel.id, {}).get('active', True)
  if message.author.bot or message.is_system() or message.guild is None or message.guild.id != config['guild'] or not sticky_active:
    return

  message_channel = bot.get_channel(message.channel.id)
  cooldown = database.data.get('sticky_messages', {}).get(message.channel.id, {}).get('cooldown', config['sticky_default_cooldown'])
  await asyncio.sleep(parse_duration(cooldown))
  last_message_id = (await _get_last_message(message_channel)).id
  if last_message_id != message.id:
    return
  sticky_content = database.data.get('sticky_messages', {}).get(message.channel.id, {}).get('value', None)
  sticky_active = database.data.get('sticky_messages', {}).get(message.channel.id, {}).get('active', True)
  if sticky_content is None or not sticky_active:
    return
  new_sticky = await message_channel.send(sticky_content)
  await _remove_last_sticky(message_channel)
  database.data.setdefault('sticky_messages', {}).setdefault(message.channel.id, {})['message_id'] = new_sticky.id

sticky = app_commands.Group(name='sticky', description='Komendy do przypiętych wiadomości')

@sticky.command(name='set', description='Ustawia przypiętą wiadomość na aktualnym kanale')
@app_commands.rename(value='wiadomość')
@app_commands.describe(value='Treść przypiętej wiadomości')
@app_commands.describe(cooldown='Minimalny odstęp czasu pomiędzy kolejnymi wiadomościami')
@app_commands.choices(cooldown=[app_commands.Choice(name=label, value=duration) for label, duration in config['sticky_cooldown_choices']])
@check_staff('zmiany przypiętych wiadomości')
async def cmd_set(interaction, value: str, cooldown: str = config['sticky_default_cooldown']):
  database.data.setdefault('sticky_messages', {}).setdefault(interaction.channel.id, {})['value'] = value
  database.data.setdefault('sticky_messages', {}).setdefault(interaction.channel.id, {})['cooldown'] = cooldown
  database.data.setdefault('sticky_messages', {}).setdefault(interaction.channel.id, {})['active'] = True
  callback_response = await interaction.response.send_message(value)
  await _remove_last_sticky(interaction.channel)
  database.data.setdefault('sticky_messages', {}).setdefault(interaction.channel.id, {})['message_id'] = callback_response.message_id

@sticky.command(name='set-cooldown', description='Ustawia minimalny odstęp czasu pomiędzy kolejnymi wiadomościami')
@app_commands.describe(cooldown='Minimalny odstęp czasu pomiędzy kolejnymi wiadomościami')
@app_commands.choices(cooldown=[app_commands.Choice(name=label, value=duration) for label, duration in config['sticky_cooldown_choices']])
@check_staff('zmiany przypiętych wiadomości')
async def cmd_set_cooldown(interaction, cooldown: str):
  database.data.setdefault('sticky_messages', {}).setdefault(interaction.channel.id, {})['cooldown'] = cooldown
  await interaction.response.send_message(f'Pomyślnie ustawiono cooldown na {cooldown} 🫡', ephemeral=True)

@sticky.command(name='pause', description='Zatrymuje wysyłanie przypiętych wiadomości')
@check_staff('zmiany przypiętych wiadomości')
async def cmd_pause(interaction):
  database.data.setdefault('sticky_messages', {}).setdefault(interaction.channel.id, {})['active'] = False
  await interaction.response.send_message('Pomyślnie zatrzymano wysyłanie przypiętych wiadomości 🫡', ephemeral=True)

@sticky.command(name='resume', description='Ponawia wysyłanie przypiętych wiadomości')
@check_staff('zmiany przypiętych wiadomości')
async def cmd_resume(interaction):
  database.data.setdefault('sticky_messages', {}).setdefault(interaction.channel.id, {})['active'] = True
  await interaction.response.send_message('Pomyślnie ponowiono wysyłanie przypiętych wiadomości 🫡', ephemeral=True)
