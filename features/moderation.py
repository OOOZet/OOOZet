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

import discord, logging
from datetime import timedelta
from itertools import chain

from common import config, debacktick, parse_duration
from features.utils import check_staff

bot = None

async def setup(_bot):
  global bot
  bot = _bot

  async def kick(interaction, member):
    if not isinstance(member, discord.Member):
      await interaction.response.send_message(f'{member.mention} nie jest już na tym serwerze… 🤨', ephemeral=True)
    elif interaction.user == member:
      await interaction.response.send_message('Nie możesz skickować samego siebie… 🤨', ephemeral=True)
    elif interaction.user.top_role <= member.top_role and interaction.user != interaction.guild.owner:
      await interaction.response.send_message(f'Nie jesteś wyżej w hierarchii od {member.mention}… 🤨', ephemeral=True)
    else:
      try:
        await member.kick(reason=f'Na żądanie {interaction.user}')
      except discord.Forbidden:
        await interaction.response.send_message(f'Nie mam uprawnień, żeby skickować {member.mention}… 🧐', ephemeral=True)
      else:
        logging.info(f'{interaction.user.id} kicked {member.id}')
        await interaction.response.send_message(f'Pomyślnie skickowano {member.mention}. 😒', ephemeral=True, allowed_mentions=discord.AllowedMentions.all())

  @bot.tree.command(name='kick', description='Kickuje użytkownika')
  @discord.app_commands.guild_only
  @check_staff('kickowania')
  async def cmd_kick(interaction, member: discord.Member):
    await kick(interaction, member)

  @bot.tree.context_menu(name='Skickuj')
  @discord.app_commands.guild_only
  @check_staff('kickowania')
  async def menu_kick(interaction, member: discord.Member):
    await kick(interaction, member)

  async def ban(interaction, user, reason):
    if interaction.user == user:
      await interaction.response.send_message('Nie możesz zbanować samego siebie… 🤨', ephemeral=True)
    elif isinstance(user, discord.Member) and interaction.user.top_role <= user.top_role and interaction.user != interaction.guild.owner:
      await interaction.response.send_message(f'Nie jesteś wyżej w hierarchii od {user.mention}… 🤨', ephemeral=True)
    else:
      try:
        await interaction.guild.ban(user, reason=f'{reason} — {interaction.user}', delete_message_seconds=0)
      except discord.Forbidden:
        await interaction.response.send_message(f'Nie mam uprawnień, żeby zbanować {user.mention}… 🧐', ephemeral=True)
      else:
        logging.info(f'{interaction.user.id} banned {user.id} for {reason!r}')
        await interaction.response.send_message(f'Pomyślnie zbanowano {user.mention} za `{debacktick(reason)}`. 😒', ephemeral=True, allowed_mentions=discord.AllowedMentions.all())

  @bot.tree.command(name='ban', description='Banuje użytkownika')
  @discord.app_commands.guild_only
  @check_staff('banowania')
  async def cmd_ban(interaction, user: discord.User, reason: str):
    await ban(interaction, user, reason)

  @bot.tree.context_menu(name='Zbanuj')
  @discord.app_commands.guild_only
  @check_staff('banowania')
  async def menu_ban(interaction, user: discord.User):
    async def on_submit(interaction2):
      await ban(interaction2, user, text_input.value)

    text_input = discord.ui.TextInput(label='Powód')
    modal = discord.ui.Modal(title=f'Zbanuj {user}')
    modal.on_submit = on_submit
    modal.add_item(text_input)
    await interaction.response.send_modal(modal)

  async def unban(interaction, user):
    try:
      await interaction.guild.unban(user, reason=f'Na żądanie {interaction.user}')
      logging.info(f'{interaction.user.id} unbanned {user.id}')
    except discord.NotFound:
      await interaction.response.send_message(f'{user.mention} nie jest obecnie zbanowany… 🤨', ephemeral=True)
    else:
      await interaction.response.send_message(f'Pomyślnie odbanowano {user.mention}! 🥳', ephemeral=True, allowed_mentions=discord.AllowedMentions.all())

  @bot.tree.command(name='unban', description='Odbanowuje użytkownika')
  @discord.app_commands.guild_only
  @check_staff('odbanowywania')
  async def cmd_unban(interaction, user: discord.User):
    await unban(interaction, user)

  @bot.tree.context_menu(name='Odbanuj')
  @discord.app_commands.guild_only
  @check_staff('odbanowywania')
  async def menu_unban(interaction, user: discord.User):
    await unban(interaction, user)

  async def purge_everywhere(interaction, user):
    async def on_submit(interaction2):
      await interaction2.response.defer()
      max_age = parse_duration(select.values[0])

      logging.info(f"{interaction.user.id} requested to purge {user.id}'s messages younger than {max_age} seconds everywhere in guild {interaction.guild.id}")

      try:
        deletedc = 0
        for channel in chain(interaction.guild.channels, interaction.guild.threads):
          if hasattr(channel, 'purge'):
            deletedc += len(await channel.purge(
              check=lambda msg: msg.author == user,
              after=interaction2.created_at - timedelta(seconds=max_age),
              reason=f'Na prośbę {interaction.user}',
              limit=None,
            ))

      except discord.Forbidden:
        await interaction2.followup.send(f'Nie mam uprawnień, żeby usuwać wiadomości… 🧐', ephemeral=True)
      else:
        await interaction2.followup.send(f'Pomyślnie usunięto {deletedc} {"wiadomość" if deletedc == 1 else "wiadomości"} użytkownika {user.mention} ze wszystkich kanałów. 😒', ephemeral=True)

    select = discord.ui.Select()
    for label, seconds in config['purge_everywhere_max_age_choices']:
      select.add_option(label=label, value=seconds)
    modal = discord.ui.Modal(title=f'Usuń wiadomości {user} wszędzie')
    modal.on_submit = on_submit
    modal.add_item(discord.ui.Label(text='Maksymalny wiek wiadomości do usunięcia', component=select))
    await interaction.response.send_modal(modal)

  @bot.tree.command(name='purge-everywhere', description='Usuwa wiadomości użytkownika ze wszystkich kanałów')
  @discord.app_commands.guild_only
  @check_staff('usuwania wiadomości')
  async def cmd_purge_everywhere(interaction, user: discord.User):
    await purge_everywhere(interaction, user)

  @bot.tree.context_menu(name='Usuń wiadomości wszędzie')
  @discord.app_commands.guild_only
  @check_staff('usuwania wiadomości')
  async def menu_purge_everywhere(interaction, user: discord.User):
    await purge_everywhere(interaction, user)
