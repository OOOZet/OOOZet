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

import asyncio, discord, discord.ext.tasks, logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import auto, Enum

import console, database
from common import config, debacktick, find, format_datetime, hybrid_check, limit_len, mention_datetime, mention_message, parse_duration, select_view
from features.utils import check_staff

bot = None

def is_ongoing(sugestia):
  return 'annulled' not in sugestia and 'outcome' not in sugestia

def is_pending(sugestia):
  return 'annulled' not in sugestia and sugestia.get('outcome', False) and 'done' not in sugestia

def is_annullable(sugestia):
  return 'annulled' not in sugestia and 'done' not in sugestia

def is_eraseable_in(interaction):
  return lambda sugestia: (sugestia['author'] == interaction.user.id or check_staff()(interaction)) and 'done' not in sugestia

def emoji_status_of(sugestia):
  if 'annulled' in sugestia:
    return '🚯'
  elif 'outcome' not in sugestia:
    return '❔'
  elif not sugestia['outcome']:
    return '❌'
  elif 'done' not in sugestia:
    return '✔️'
  else:
    return '✅'

def view_for(sugestia):
  view = discord.ui.View(timeout=None)
  view.add_item(discord.ui.Button(custom_id='for', label=f'Za ({len(sugestia["for"])})', style=discord.ButtonStyle.green))
  view.add_item(discord.ui.Button(custom_id='abstain', label=f'Nie wiem ({len(sugestia["abstain"])})', style=discord.ButtonStyle.gray))
  view.add_item(discord.ui.Button(custom_id='against', label=f'Przeciw ({len(sugestia["against"])})', style=discord.ButtonStyle.red))

  # This breaks on sugestia deletion or when the sugestia object in database.data changes, e.g. after database.load. There may be other such edge cases in the codebase.
  async def on_vote(interaction):
    user = interaction.user.id
    choice = interaction.data['custom_id']

    if interaction.user.bot:
      await interaction.response.send_message('Boty nie mogą głosować nad sugestiami… 🤨', ephemeral=True)
    elif config['sugestie_vote_role'] is not None and interaction.user.get_role(config['sugestie_vote_role']) is None:
      await interaction.response.send_message(f'Nie masz jeszcze roli <@&{config["sugestie_vote_role"]}> i nie możesz głosować nad sugestiami. 😢', ephemeral=True)
    elif interaction.created_at >= sugestia['vote_end']:
      await interaction.response.send_message('Głosowanie nad tą sugestią już się skończyło. ⏱️', ephemeral=True)
    elif user in sugestia[choice]:
      await interaction.response.send_message('Już zagłosowałeś na tę opcję… 🤨', ephemeral=True)
    else:
      with database.lock:
        is_change_of_mind = False
        for i in ['for', 'abstain', 'against']:
          if user in sugestia[i]:
            is_change_of_mind = True
            sugestia[i].remove(user)
        sugestia[choice].add(user)
        database.should_save = True

      if is_change_of_mind:
        logging.info(f'{user} has changed their vote to {choice!r} on sugestia {sugestia["id"]}')
        replies = {
          'for': 'Pomyślnie zmieniono głos na **za** sugestią. 🫡',
          'abstain': 'Pomyślnie zmieniono głos na **wstrzymanie się** od głosu. 🫡',
          'against': 'Pomyślnie zmieniono głos na **przeciw** sugestii. 🫡',
        }
      else:
        logging.info(f'{user} has voted {choice!r} on sugestia {sugestia["id"]}')
        replies = {
          'for': 'Pomyślnie zagłosowano **za** sugestią. 🫡',
          'abstain': 'Pomyślnie **wstrzymano się** od głosu. 🫡',
          'against': 'Pomyślnie zagłosowano **przeciw** sugestii. 🫡',
        }
      await interaction.response.send_message(replies[choice], ephemeral=True)

    await update(sugestia)

  if is_ongoing(sugestia):
    for button in view.children:
      button.callback = on_vote
  else:
    for button in view.children:
      button.disabled = True

  async def on_describe(interaction):
    vote_end = mention_datetime(sugestia['vote_end'])
    if 'outcome' in sugestia:
      result = f'Głosowanie zakończyło się {vote_end} wynikiem '
      if sugestia['outcome']:
        result += '**pozytywnym**. ✅\n'
      else:
        result += '**negatywnym**. ❌\n'
    elif 'annulled' in sugestia:
      result = f'Głosowanie miało skończyć się {vote_end}.\n'
    else:
      result = f'**Głosowanie jeszcze trwa** i skończy się {vote_end}. ❔\n'

    if sugestia['for']:
      voters = ', '.join(f'<@{i}>' for i in sugestia['for'])
      result += f'- Głosowali **za**: {voters}\n'
    else:
      result += '- **Nikt** nie głosował **za**.\n'

    if sugestia['abstain']:
      voters = ', '.join(f'<@{i}>' for i in sugestia['abstain'])
      result += f'- **Wstrzymali się** od głosu: {voters}\n'
    else:
      result += '- **Nikt** nie **wstrzymał się** od głosu.\n'

    if sugestia['against']:
      voters = ', '.join(f'<@{i}>' for i in sugestia['against'])
      result += f'- Głosowali **przeciw**: {voters}\n'
    else:
      result += '- **Nikt** nie głosował **przeciw**.\n'

    if 'annulled' in sugestia:
      time = mention_datetime(sugestia['annulled']['time'])
      reason = debacktick(sugestia['annulled']['reason'])
      result += f'Sugestia **została unieważniona** {time} z powodu `{reason}`. 🚯\n'
    elif sugestia.get('outcome', False):
      if 'done' in sugestia:
        time = mention_datetime(sugestia['done']['time'])
        changes = debacktick(sugestia['done']['changes'])
        result += f'Sugestia **została wykonana** {time} z opisem zmian `{changes}` ✅\n'
      else:
        result += 'Sugestia **nie została jeszcze wykonana** przez administrację. ❓\n'

    await interaction.response.send_message(result, ephemeral=True)

  describe_button = discord.ui.Button(custom_id='describe', label='Więcej informacji', style=discord.ButtonStyle.blurple)
  describe_button.callback = on_describe
  view.add_item(describe_button)

  return view

async def update(sugestia):
  logging.info(f'Updating sugestia {sugestia["id"]}')

  if is_ongoing(sugestia):
    with database.lock:
      if config['sugestie_deciding_lead'] is not None and abs(len(sugestia['for']) - len(sugestia['against'])) >= config['sugestie_deciding_lead']:
        sugestia['vote_end'] = datetime.now().astimezone()
        database.should_save = True

      if datetime.now().astimezone() >= sugestia['vote_end']:
        sugestia['outcome'] = len(sugestia['for']) > len(sugestia['against'])
        database.should_save = True

        if sugestia['outcome']:
          logging.info(f'Sugestia {sugestia["id"]} has passed')
        else:
          logging.info(f'Sugestia {sugestia["id"]} did not pass')

  try:
    await bot.get_channel(sugestia['channel']).get_partial_message(sugestia['id']).edit(view=view_for(sugestia))
  except discord.errors.NotFound:
    logging.warn(f'Sugestia {sugestia["id"]} is missing')

async def update_all():
  logging.info('Updating all sugestie')
  for sugestia in database.data.get('sugestie', []):
    await update(sugestia)

async def update_on_vote_end(sugestia):
  delay = (sugestia['vote_end'] - datetime.now().astimezone()).total_seconds() + 5 # 5 seconds to make sure the if passes.
  logging.info(f'Waiting {delay} seconds to update sugestia {sugestia["id"]}')
  await asyncio.sleep(delay)
  await update(sugestia)

cleaning_lock = asyncio.Lock()
async def clean():
  if config['sugestie_channel'] is None:
    return

  if 'sugestie_clean_until' not in database.data:
    logging.info('#sugestie has never been cleaned before')
    database.data['sugestie_clean_until'] = datetime.now().astimezone()
    database.should_save = True

  async with cleaning_lock:
    async for msg in bot.get_channel(config['sugestie_channel']).history(limit=None, after=database.data['sugestie_clean_until']):
      if msg.author == bot.user:
        continue

      await msg.delete()
      if msg.author.bot:
        continue

      embed = discord.Embed(title='Sugestia', description=msg.content)
      embed.set_footer(text=msg.author.our_name, icon_url=msg.author.display_avatar.url)
      my_msg = await msg.channel.send(embed=embed)

      logging.info(f'{msg.author.id} created sugestia {my_msg.id}')
      sugestia = {
        'id': my_msg.id,
        'channel': my_msg.channel.id,
        'text': msg.content,
        'author': msg.author.id,
        'for': set(),
        'abstain': set(),
        'against': set(),
        'vote_start': my_msg.created_at,
        'vote_end': my_msg.created_at + timedelta(seconds=parse_duration(config['sugestie_vote_length'])),
      }
      database.data.setdefault('sugestie', []).append(sugestia)
      database.data['sugestie_clean_until'] = msg.created_at
      database.should_save = True

      await update(sugestia)
      asyncio.create_task(update_on_vote_end(sugestia))

      if config['sugestie_ping_role'] is not None:
        await (await msg.channel.send(f'<@&{config["sugestie_ping_role"]}>')).delete()

@dataclass
class NoSugestieError(discord.app_commands.CheckFailure):
  class Filter(Enum):
    Any = auto()
    Pending = auto()
    Annullable = auto()
    Eraseable = auto()
  filter: Filter

@hybrid_check
def check_any(interaction):
  if not database.data.get('sugestie', []):
    raise NoSugestieError(NoSugestieError.Filter.Any)

@hybrid_check
def check_pending(interaction):
  if not any(map(is_pending, database.data.get('sugestie', []))):
    raise NoSugestieError(NoSugestieError.Filter.Pending)

@hybrid_check
def check_annullable(interaction):
  if not any(map(is_annullable, database.data.get('sugestie', []))):
    raise NoSugestieError(NoSugestieError.Filter.Annullable)

@hybrid_check
def check_eraseable(interaction):
  if not any(map(is_eraseable_in(interaction), database.data.get('sugestie', []))):
    raise NoSugestieError(NoSugestieError.Filter.Eraseable)

async def setup(_bot):
  global bot
  bot = _bot

  @bot.on_check_failure
  async def on_check_failure(interaction, error):
    if isinstance(error, NoSugestieError):
      match error.filter:
        case error.Filter.Any:
          await interaction.response.send_message('Nie zostały jeszcze przedłożone żadne sugestie… 🤨', ephemeral=True)
        case error.Filter.Pending:
          await interaction.response.send_message('Nie ma żadnych sugestii, które zostały jeszcze do wykonania… 🤨', ephemeral=True)
        case error.Filter.Annullable:
          await interaction.response.send_message('Nie ma żadnych sugestii, które możesz unieważnić… 🤨', ephemeral=True)
        case error.Filter.Eraseable:
          await interaction.response.send_message('Nie ma żadnych sugestii, które możesz usunąć… 🤨', ephemeral=True)
    else:
      raise

  @bot.listen()
  async def on_ready():
    logging.info('Cleaning #sugestie')
    await clean()

    for sugestia in database.data.get('sugestie', []):
      bot.add_view(view_for(sugestia), message_id=sugestia['id'])
      if is_ongoing(sugestia):
        asyncio.create_task(update_on_vote_end(sugestia))

    logging.info('Sugestie is ready')

  @bot.listen()
  async def on_message(msg):
    if msg.channel.id == config['sugestie_channel'] and msg.author != bot.user:
      logging.info('Cleaning #sugestie after a new message')
      await clean() # Same pattern as in counting.py

  sugestie = discord.app_commands.Group(name='sugestie', description='Komendy do sugestii', guild_ids=[config['guild']])
  bot.tree.add_command(sugestie)

  @sugestie.command(description='Wyświetla sugestię')
  @check_any
  async def show(interaction):
    async def callback(interaction2, choice):
      sugestia = find(int(choice), database.data['sugestie'], proj=lambda x: x['id'])
      embed = discord.Embed(title=mention_message(bot, sugestia['channel'], sugestia['id']), description=sugestia['text'])
      await interaction2.response.send_message(embed=embed, ephemeral=True)

    await interaction.response.send_message('Którą sugestię chcesz zobaczyć?', view=select_view(
      list(map(
        lambda sugestia: discord.SelectOption(
          label=limit_len(sugestia['text']),
          value=sugestia['id'],
          description=format_datetime(sugestia['vote_start']),
          emoji=emoji_status_of(sugestia),
        ),
        reversed(database.data['sugestie']),
      )),
      callback,
      interaction.user,
    ), ephemeral=True)

  @sugestie.command(description='Oznacza sugestię jako wykonaną')
  @check_pending
  @check_staff('wykonywania sugestii')
  async def done(interaction, changes: str):
    async def callback(interaction2, choice):
      sugestia = find(int(choice), filter(is_pending, database.data['sugestie']), proj=lambda x: x['id'])

      logging.info(f'{interaction2.user.id} has marked sugestia {sugestia["id"]} as done')
      sugestia['done'] = {
        'time': interaction2.created_at,
        'changes': changes,
      }
      database.should_save = True

      msg = mention_message(bot, sugestia['channel'], sugestia['id'])
      await interaction.edit_original_response(content=f'Pomyślnie oznaczono sugestię {msg} jako wykonaną z opisem zmian `{debacktick(changes)}`! 🥳', view=None)
      await interaction2.response.defer()

    await interaction.response.send_message(f'Którą sugestię chcesz oznaczyć jako wykonaną z opisem zmian `{debacktick(changes)}`?', view=select_view(
      list(map(
        lambda sugestia: discord.SelectOption(
          label=limit_len(sugestia['text']),
          value=sugestia['id'],
          description=format_datetime(sugestia['vote_start']),
        ),
        filter(is_pending, reversed(database.data['sugestie'])),
      )),
      callback,
      interaction.user,
    ))

  @sugestie.command(description='Unieważnia sugestię')
  @check_annullable
  @check_staff('unieważniania sugestii')
  async def annul(interaction, reason: str):
    async def callback(interaction2, choice):
      sugestia = find(int(choice), filter(is_annullable, database.data['sugestie']), proj=lambda x: x['id'])

      logging.info(f'{interaction2.user.id} has annulled sugestia {sugestia["id"]}')
      sugestia['annulled'] = {
        'time': interaction2.created_at,
        'reason': reason,
      }
      database.should_save = True

      msg = mention_message(bot, sugestia['channel'], sugestia['id'])
      await interaction.edit_original_response(content=f'Pomyślnie unieważniono sugestię {msg} z powodu `{debacktick(reason)}`. 🙄', view=None)
      await interaction2.response.defer()

      await update(sugestia)

    await interaction.response.send_message(f'Którą sugestię chcesz unieważnić z powodu `{debacktick(reason)}`?', view=select_view(
      list(map(
        lambda sugestia: discord.SelectOption(
          label=limit_len(sugestia['text']),
          value=sugestia['id'],
          description=format_datetime(sugestia['vote_start']),
          emoji=emoji_status_of(sugestia),
        ),
        filter(is_annullable, reversed(database.data['sugestie'])),
      )),
      callback,
      interaction.user,
    ))

  @sugestie.command(description='Usuwa pomyłkowo wysłaną sugestię')
  @check_eraseable
  async def erase(interaction):
    async def callback(interaction2, choice):
      sugestia = find(int(choice), filter(is_eraseable_in(interaction2), database.data['sugestie']), proj=lambda x: x['id'])

      logging.info(f'{interaction2.user.id} has erased sugestia {sugestia["id"]}')
      database.data['sugestie'].remove(sugestia)
      try:
        await bot.get_channel(sugestia['channel']).get_partial_message(sugestia['id']).delete()
      except discord.errors.NotFound:
        pass

      await interaction.edit_original_response(content=f'Pomyślnie usunięto sugestię o treści `{limit_len(debacktick(sugestia["text"]))}`. 🙄', view=None)
      await interaction2.response.defer()

    await interaction.response.send_message(f'Którą sugestię chcesz usunąć?', view=select_view(
      list(map(
        lambda sugestia: discord.SelectOption(
          label=limit_len(sugestia['text']),
          value=sugestia['id'],
          description=format_datetime(sugestia['vote_start']),
          emoji=emoji_status_of(sugestia),
        ),
        filter(is_eraseable_in(interaction), reversed(database.data['sugestie'])),
      )),
      callback,
      interaction.user,
    ))

console.begin('sugestie')
console.register('update_all', None, 'updates all sugestie', lambda: asyncio.run_coroutine_threadsafe(update_all(), bot.loop).result())
console.end()
