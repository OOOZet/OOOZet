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

import discord, logging
from io import StringIO

import database
from common import config, find, format_datetime, hybrid_check, mention_datetime, select_view
from features import sugestie
from features.utils import check_staff

class NoRulesError(discord.app_commands.CheckFailure):
  pass

@hybrid_check
def check_rules(interaction):
  if not database.data.get('rules', []):
    raise NoRulesError()

def setup(bot):
  pass_error_on = bot.tree.on_error
  @bot.tree.error
  async def on_error(interaction, error):
    if isinstance(error, NoRulesError):
      await interaction.response.send_message(f'Nie został jeszcze ustanowiony żaden regulamin… 🤨', ephemeral=True)
    else:
      await pass_error_on(interaction, error)

  rules = discord.app_commands.Group(name='rules', description='Komendy do regulaminu', guild_ids=[config['guild']])
  bot.tree.add_command(rules)

  @rules.command(description='Wyświetla obowiązujący regulamin')
  @check_rules
  async def show(interaction):
    result = max(database.data['rules'], key=lambda x: x['time'])['text']
    await interaction.response.send_message(
      f'Załączam regulamin obowiązujący na serwerze. 😉',
      file=discord.File(StringIO(result), 'rules.md'),
      ephemeral=True,
    )

  @rules.command(description='Wyświetla historyczne wersje regulaminu')
  @check_rules
  async def history(interaction):
    async def callback(interaction2, choice):
      result = find(int(choice), database.data['rules'], proj=id)
      await interaction2.response.send_message(
        f'Załączam regulamin z dnia {mention_datetime(result["time"])}. 😉',
        file=discord.File(StringIO(result['text']), 'rules.md'),
        ephemeral=True,
      )

    select, view = select_view(callback, interaction.user)
    for rules in database.data['rules']:
      select.add_option(label=format_datetime(rules['time']), value=id(rules))
    await interaction.response.send_message('Którą wersję regulaminu chcesz zobaczyć?', view=view, ephemeral=True)

  async def resend(interaction):
    if not interaction.response.is_done():
      await interaction.response.defer(ephemeral=True)

    assert(interaction.guild.id == config['guild'])
    channel = interaction.guild.rules_channel
    if channel is None:
      await interaction.followup.send('Nie został jeszcze ustawiony żaden kanał z zasadami… 🤨', ephemeral=True)
      return

    await channel.purge() # This will delete at most 100 messages in case there was a mistake.
    text = max(database.data['rules'], key=lambda x: x['time'])['text']
    fragments = iter(filter(lambda x: x, text.split('\n\n')))
    await channel.send(next(fragments))
    for fragment in fragments:
      await channel.send('_ _\n' + fragment)

    await interaction.followup.send('Pomyślnie zaaktualizowano kanał z regulaminem. 🫡', ephemeral=True)

  @rules.command(name='resend', description='Aktualizuje kanał z regulaminem')
  @check_rules
  @check_staff('aktualizowania kanału z regulaminem')
  async def cmd_resend(interaction):
    await resend(interaction)

  @rules.command(description='Ustanawia nowy regulamin')
  @check_staff('ustanawiania nowego regulaminu')
  async def set(interaction, text: discord.Attachment, sugestia: bool):
    try:
      text = (await text.read()).decode().replace('\r\n', '\n')
    except UnicodeDecodeError:
      await interaction.response.send_message('Załączony regulamin musi być plikiem tekstowym… 🤨', ephemeral=True)
      return

    async def callback(interaction2, choice):
      sugestia = int(choice) if choice is not None else None
      logging.info('Setting new rules' + (f' thanks to sugestia {sugestia}' if sugestia is not None else ''))
      rules = {
        'time': interaction2.created_at,
        'text': text,
        'sugestia': sugestia,
      }
      database.data.setdefault('rules', []).append(rules)
      database.should_save = True

      if interaction.response.is_done():
        await interaction.edit_original_response(content='Pomyślnie ustanowiono nowy regulamin. 🫡', view=None)
      else:
        await interaction.response.send_message('Pomyślnie ustanowiono nowy regulamin. 🫡')

      await resend(interaction2)

    if sugestia:
      sugestie.check_pending()
      select, view = select_view(callback, interaction.user)
      for sugestia in filter(sugestie.is_pending, database.data['sugestie']):
        select.add_option(label=sugestia['text'], value=sugestia['id'], description=format_datetime(sugestia['vote_start']))
      await interaction.response.send_message('Z którą sugestią jest powiązana ta zmiana regulaminu?', view=view)
    else:
      await callback(interaction, None)
