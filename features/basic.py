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

import discord, pprint, random
from datetime import datetime

import bot, database
from common import config, parse_duration

@bot.tree.command(name='config', description='Wyświetla konfigurację bota')
async def _config(interaction):
  result = config.copy()
  del result['token']
  result = pprint.pformat(result, sort_dicts=False)
  await interaction.response.send_message(f'Moja wewnętrzna konfiguracja wygląda następująco:```json\n{result}```', ephemeral=True)

@bot.tree.command(description='Dziękuje istotnym twórcom bota')
async def credits(interaction):
  await interaction.response.send_message('OOOZet powstał dzięki wspólnym staraniom <@671790729676324867>, <@386516541790748673>, <@536253933778370580> i innych. :slight_smile:', ephemeral=True)

@bot.tree.command(description='Sprawdza ping bota')
async def ping(interaction):
  delay = (datetime.now().astimezone() - interaction.created_at).total_seconds()
  await interaction.response.send_message(f'Pong! `{1000 * delay:.0f}ms`', ephemeral=True)

@bot.tree.command(description='Wzywa administrację na ratunek')
async def alarm(interaction):
  staff = {i for role in config['staff_roles'] for i in interaction.guild.get_role(role).members}

  if not staff:
    await interaction.response.send_message('Hmm, z jakiegoś powodu nie jest mi znane, żeby ktoś był w administracji… :face_with_raised_eyebrow:')
    return

  now = datetime.now().astimezone()

  if 'alarm_last' in database.data:
    last = datetime.fromisoformat(database.data['alarm_last'])
    cooldown = parse_duration(config['alarm_cooldown'])
    if (now - last).total_seconds() < cooldown:
      await interaction.response.send_message(f'Alarm już zabrzmiał w przeciągu ostatnich {cooldown} sekund. :stopwatch:', ephemeral=True)
      return

  database.data['alarm_last'] = now.isoformat()
  database.should_save = True

  emoji = random.choice([':worried:', ':confounded:', ':scream:', ':open_mouth:', ':dizzy_face:', ':face_with_spiral_eyes:', ':woozy_face:'])

  await interaction.response.send_message(f'{" ".join(i.mention for i in staff)} Potrzebna natychmiastowa interwencja!!! {emoji}')

  for user in staff:
    await user.send(f'{interaction.user.mention} potrzebuje natychmiastowej interwencji na OOOZ!!! {emoji}')
    await user.send('https://c.tenor.com/EDeg5ifIrjQAAAAC/alarm-better-discord.gif')

async def update_warn_role_for(user):
  roles = [user.guild.get_role(i) for i in config['warn_roles']]
  await user.remove_roles(*roles)
  count = len(database.data.get('warns', {}).get(user.id, []))
  if count > 0 and roles:
    await user.add_roles(roles[min(count, len(roles)) - 1])

@bot.tree.command(description='Warnuje użytkownika')
async def warn(interaction, user: discord.Member, reason: str):
  if not any(interaction.user.get_role(i) is not None for i in config['staff_roles']):
    await interaction.response.send_message('Nie masz uprawnień do warnowania, tylko administracja może to robić. :rage:', ephemeral=True)
    return

  warn = {
    'time': datetime.now().astimezone().isoformat(),
    'reason': reason,
  }
  database.data.setdefault('warns', {}).setdefault(user.id, []).append(warn)
  database.should_save = True
  count = len(database.data['warns'][user.id])

  await update_warn_role_for(user)

  await interaction.response.send_message(f'{user.mention} właśnie dostał swojego {count}-ego warna za `{reason.replace("`", "")}`! :unamused:')

@bot.tree.context_menu(name='Odbierz warna')
async def unwarn(interaction, user: discord.Member):
  if not any(interaction.user.get_role(i) is not None for i in config['staff_roles']):
    await interaction.response.send_message('Nie masz uprawnień do odbierania warnów, tylko administracja może to robić. :rage:', ephemeral=True)
    return

  warns = database.data.get('warns', {}).get(user.id, [])

  if not warns:
    await interaction.response.send_message(f'{user.mention} jest grzeczny jak aniołek i nie nazbierał jeszcze żadnych warnów! :innocent:', ephemeral=True)
    return

  async def callback(interaction2):
    warn = next(filter(lambda x: id(x) == int(choice.values[0]), warns))
    warns.remove(warn)
    database.should_save = True

    await update_warn_role_for(user)

    timestamp = int(datetime.fromisoformat(warn['time']).timestamp())
    reason = warn['reason'].replace('`', '')
    await interaction.edit_original_response(content=f'Pomyślnie odebrano warna `{reason}` z dnia <t:{timestamp}> użytkownikowi {user.mention}! :partying_face:', view=None)

    await interaction2.response.defer()

  choice = discord.ui.Select()
  choice.callback = callback
  view = discord.ui.View()
  view.add_item(choice)
  async def interaction_check(interaction2):
    return interaction2.user == interaction.user
  view.interaction_check = interaction_check

  for warn in warns:
    time = datetime.fromisoformat(warn['time'])
    choice.add_option(
      label=warn['reason'],
      value=id(warn),
      description=f'{time.day} {time:%B} {time:%Y} {time:%H}:{time:%M}',
    )

  await interaction.response.send_message(f'Którego warna chcesz odebrać użytkownikowi {user.mention}?', view=view)

@bot.tree.context_menu(name='Pokaż warny')
async def warns(interaction, user: discord.Member):
  warns = database.data.get('warns', {}).get(user.id, [])
  if warns:
    result = random.choice([
      f'{user.mention} ma już na swoim koncie parę złych uczynków… :pensive:',
      f'Do {user.mention} nie przyjdzie Mikołaj w tym roku… :confused:',
      f'Na {user.mention} czeka już tylko czyściec… :weary:',
    ])

    for warn in warns:
      timestamp = int(datetime.fromisoformat(warn['time']).timestamp())
      reason = warn['reason'].replace('`', '')
      result += f'\n- `{reason}` w dniu <t:{timestamp}>'

    await interaction.response.send_message(result, ephemeral=True)
  else:
    await interaction.response.send_message(f'{user.mention} jest grzeczny jak aniołek i nie nazbierał jeszcze żadnych warnów! :innocent:', ephemeral=True)
