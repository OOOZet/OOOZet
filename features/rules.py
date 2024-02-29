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
from common import config, find, format_datetime, hybrid_check, limit_len, mention_datetime, select_view
from features import sugestie
from features.utils import check_staff

class NoRulesError(discord.app_commands.CheckFailure):
  pass

@hybrid_check
def check_rules(interaction):
  if not database.data.get('rules', []):
    raise NoRulesError()

def setup(bot):
  @bot.on_check_failure
  async def on_check_failure(interaction, error):
    if isinstance(error, NoRulesError):
      await interaction.response.send_message(f'Nie został jeszcze ustanowiony żaden regulamin… 🤨', ephemeral=True)
    else:
      raise

  rules = discord.app_commands.Group(name='rules', description='Komendy do regulaminu', guild_ids=[config['guild']])
  bot.tree.add_command(rules)

  @rules.command(description='Wyświetla obowiązujący regulamin')
  @check_rules
  async def show(interaction):
    result = max(database.data['rules'], key=lambda x: x['time'])['text'] + '\n'
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
        file=discord.File(StringIO(result['text'] + '\n'), 'rules.md'),
        ephemeral=True,
      )

    select, view = select_view(callback, interaction.user)
    for rules in database.data['rules']:
      select.add_option(label=format_datetime(rules['time']), value=id(rules))
    await interaction.response.send_message('Którą wersję regulaminu chcesz zobaczyć?', view=view, ephemeral=True)

  def fragment_text(string):
    fragment = []
    for line in string.splitlines():
      line = line or '_ _'
      if (line == '_ _' or line.startswith('#')) and fragment and fragment[-1] != '_ _':
        yield '\n'.join(fragment)
        fragment = []
      fragment.append(line)
    if fragment:
      yield '\n'.join(fragment)

  async def resend(interaction):
    if not interaction.response.is_done():
      await interaction.response.defer(ephemeral=True)

    assert interaction.guild.id == config['guild']
    channel = interaction.guild.rules_channel
    if channel is None:
      await interaction.followup.send('Nie został jeszcze ustawiony żaden kanał z zasadami… 🤨', ephemeral=True)
      return

    await channel.purge() # This will delete at most 100 messages in case there was a mistake.
    text = max(database.data['rules'], key=lambda x: x['time'])['text']
    for fragment in fragment_text(text):
      await channel.send(fragment)

    await interaction.followup.send('Pomyślnie zaaktualizowano kanał z regulaminem. 🫡', ephemeral=True)

  @rules.command(name='resend', description='Aktualizuje kanał z regulaminem')
  @check_rules
  @check_staff('aktualizowania kanału z regulaminem')
  async def cmd_resend(interaction):
    await resend(interaction)

  @rules.command(name='set', description='Ustanawia nowy regulamin')
  @check_staff('ustanawiania nowego regulaminu')
  async def set_(interaction, text: discord.Attachment, ile_sugestii: discord.app_commands.Range[int, 0, 4]): # Max is 4 due to a limitation in Discord.
    try:
      text = (await text.read()).decode()
      text = '\n'.join(line.rstrip() for line in text.strip().splitlines())
    except UnicodeDecodeError:
      await interaction.response.send_message('Załączony regulamin musi być plikiem tekstowym… 🤨', ephemeral=True)
      return
    if not text:
      await interaction.response.send_message('Regulamin nie może być pusty… 🤨', ephemeral=True)
      return
    if any(len(i) > 2000 for i in fragment_text(text)):
      await interaction.response.send_message('Regulamin nie może zawierać paragrafy dłuższe niż ~2000 znaków. 😊', ephemeral=True)
      return

    if sum(map(sugestie.is_pending, database.data.get('sugestie', []))) < ile_sugestii:
      await interaction.response.send_message(f'Nie ma co najmniej **{ile_sugestii}** sugestii, które zostały jeszcze do wykonania… 🤨', ephemeral=True)
      return

    async def on_submit(interaction2):
      logging.info('Setting new rules')
      rules = {
        'time': interaction2.created_at,
        'text': text,
        'sugestie': [int(select.values[0]) for select in view.children[:-1]] if ile_sugestii > 0 else [],
      }
      database.data.setdefault('rules', []).append(rules)
      database.should_save = True

      if interaction.response.is_done():
        await interaction.edit_original_response(content='Pomyślnie ustanowiono nowy regulamin. 🫡', view=None)
      else:
        await interaction.response.send_message('Pomyślnie ustanowiono nowy regulamin. 🫡')

      await resend(interaction2)

    if ile_sugestii == 0:
      await on_submit(interaction)
    else:
      view = discord.ui.View()
      async def interaction_check(interaction2):
        return interaction2.user == interaction.user
      view.interaction_check = interaction_check

      for i in range(ile_sugestii):
        async def callback(interaction):
          await interaction.response.defer()

          selected_sugestie = set()
          for select in view.children[:-1]:
            if select.values:
              selected_sugestie.add(int(select.values[0]))
            for option in select.options:
              option.default = bool(select.values) and int(option.value) == int(select.values[0])
          submit.disabled = len(selected_sugestie) != ile_sugestii
          await interaction.edit_original_response(view=view)

        select = discord.ui.Select()
        select.callback = callback
        for sugestia in filter(sugestie.is_pending, database.data['sugestie']):
          select.add_option(label=limit_len(sugestia['text']), value=sugestia['id'], description=format_datetime(sugestia['vote_start']))
        view.add_item(select)

      submit = discord.ui.Button(style=discord.ButtonStyle.success, label='Zatwierdź')
      submit.callback = on_submit
      submit.disabled = True
      view.add_item(submit)

      await interaction.response.send_message('Z którymi sugestiami jest powiązana ta zmiana regulaminu?', view=view)
