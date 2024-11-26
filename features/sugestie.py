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
from base64 import b64decode, b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import auto, Enum
from io import BytesIO
from mimetypes import guess_extension

import console, database
from common import config, debacktick, format_datetime, hybrid_check, limit_len, mention_datetime, mention_message, parse_duration, select_view, sleep_until
from features.utils import check_staff, is_staff

bot = None

def is_ongoing(sugestia):
  return 'annulled' not in sugestia and 'outcome' not in sugestia

def is_pending(sugestia):
  return 'annulled' not in sugestia and sugestia.get('outcome', False) and 'done' not in sugestia

def is_annullable(sugestia):
  return 'annulled' not in sugestia and 'done' not in sugestia

def is_eraseable_in(interaction):
  return lambda sugestia: (sugestia['author'] == interaction.user.id or is_staff(interaction.user)) and 'done' not in sugestia

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

async def update_embed(sugestia):
  msg = await bot.get_channel(sugestia['channel']).fetch_message(sugestia['id'])
  embed = msg.embeds[0]

  embed.clear_fields()
  for author, comment in sorted(sugestia['comments'].items(), key=lambda x: x[1]['time']):
    embed.add_field(name=(await bot.fetch_user(author)).our_name.replace('_', '\\_') + ':', value=comment['text'], inline=False)

  if sugestia['image'] is None:
    embed.set_thumbnail(url=None)
    await msg.edit(embed=embed, attachments=[])
  else:
    filename = 'sugestia' + guess_extension(sugestia['image']['format'])
    embed.set_thumbnail(url=f'attachment://{filename}')
    await msg.edit(embed=embed, attachments=[discord.File(BytesIO(b64decode(sugestia['image']['data'])), filename)])

def view_for(sugestia):
  view = discord.ui.View(timeout=None)

  if sugestia.get('annulled', {}).get('time', datetime.now().astimezone()) < sugestia['review_end']:
    async def on_comment(interaction):
      if config['sugestie_role'] is not None and interaction.user.get_role(config['sugestie_role']) is None:
        await interaction.response.send_message(f'Nie masz jeszcze roli <@&{config["sugestie_role"]}> i nie możesz komentować sugestii. 😢', ephemeral=True)
        return
      if interaction.created_at >= sugestia['review_end']:
        await interaction.response.send_message('Czas na komentowanie tej sugestii już się skończył. ⏱️', ephemeral=True)
        return

      async def on_submit(interaction2):
        if config['sugestie_role'] is not None and interaction2.user.get_role(config['sugestie_role']) is None:
          await interaction2.response.send_message(f'Nie masz jeszcze roli <@&{config["sugestie_role"]}> i nie możesz komentować sugestii. 😢', ephemeral=True)
        elif interaction2.created_at >= sugestia['review_end']:
          await interaction2.response.send_message('Czas na komentowanie tej sugestii już się skończył. ⏱️', ephemeral=True)
        else:
          logging.info(f'{interaction2.user.id} has commented on sugestia {sugestia["id"]}')
          sugestia['comments'][interaction2.user.id] = {
            'text': text_input.value,
            'time': interaction2.created_at,
          }
          database.should_save = True

          await update_embed(sugestia)

          msg = mention_message(bot, sugestia['channel'], sugestia['id'])
          await interaction2.response.send_message(f'Pomyślnie dodano komentarz do sugestii {msg}! 🥳', ephemeral=True)

      text_input = discord.ui.TextInput(
        default=sugestia['comments'].get(interaction.user.id, {}).get('text'),
        label='Komentarz',
        max_length=1024,
        style=discord.TextStyle.long,
      )
      modal = discord.ui.Modal(title='Skomentuj sugestię')
      modal.on_submit = on_submit
      modal.add_item(text_input)
      await interaction.response.send_modal(modal)

    comment = discord.ui.Button(custom_id='comment', label='Skomentuj', style=discord.ButtonStyle.green)
    comment.callback = on_comment
    view.add_item(comment)

    async def on_delete(interaction):
      msg = mention_message(bot, sugestia['channel'], sugestia['id'])

      if is_staff(interaction.user):
        if not sugestia['comments']:
          await interaction.response.send_message(f'Nie zostały jeszcze dodane żadne komentarze do tej sugestii… 🤨', ephemeral=True)
          return

        async def callback(interaction2, choice):
          check_staff('usuwania komentarzy')(interaction2)
          author = int(choice)

          logging.info(f"{interaction.user.id} has removed {author}'s comment from sugestia {sugestia['id']}")
          del sugestia['comments'][author]
          database.should_save = True

          await update_embed(sugestia)

          await interaction2.response.send_message(f'Pomyślnie usunięto komentarz <@{author}> do sugestii {msg}. 🙄', ephemeral=True)

        await interaction.response.send_message('Który komentarz chcesz usunąć?', view=select_view(
          [
            discord.SelectOption(label=limit_len(comment['text']), value=author, description=(await bot.fetch_user(author)).our_name)
            for author, comment in sugestia['comments'].items()
          ],
          callback,
          interaction.user,
        ), ephemeral=True)

      else:
        if interaction.user.id not in sugestia['comments']:
          await interaction.response.send_message(f'Nie dodałeś żadnego komentarza do tej sugestii… 🤨', ephemeral=True)
          return

        logging.info(f'{interaction.user.id} has removed their comment from sugestia {sugestia["id"]}')
        del sugestia['comments'][interaction.user.id]
        database.should_save = True

        await update_embed(sugestia)

        await interaction.response.send_message(f'Pomyślnie usunięto twój komentarz do sugestii {msg}. 🫡', ephemeral=True)

    delete = discord.ui.Button(custom_id='delete', label='Usuń komentarz', style=discord.ButtonStyle.red)
    delete.callback = on_delete
    view.add_item(delete)

    if 'annulled' in sugestia:
      for button in view.children:
        button.disabled = True

  else:
    view.add_item(discord.ui.Button(custom_id='for', label=f'Za ({len(sugestia["for"])})', style=discord.ButtonStyle.green))
    view.add_item(discord.ui.Button(custom_id='abstain', label=f'Nie wiem ({len(sugestia["abstain"])})', style=discord.ButtonStyle.gray))
    view.add_item(discord.ui.Button(custom_id='against', label=f'Przeciw ({len(sugestia["against"])})', style=discord.ButtonStyle.red))

    # This breaks on sugestia deletion or when the sugestia object in database.data changes, e.g. after database.load. There may be other such edge cases in the codebase.
    async def on_vote(interaction):
      user = interaction.user.id
      choice = interaction.data['custom_id']

      if config['sugestie_role'] is not None and interaction.user.get_role(config['sugestie_role']) is None:
        await interaction.response.send_message(f'Nie masz jeszcze roli <@&{config["sugestie_role"]}> i nie możesz głosować nad sugestiami. 😢', ephemeral=True)
      elif interaction.created_at < sugestia['review_end']:
        await interaction.response.send_message('Głosowanie nad tą sugestią jeszcze się nie zaczęło. ⏱️', ephemeral=True)
      elif interaction.created_at >= sugestia['vote_end']:
        await interaction.response.send_message('Głosowanie nad tą sugestią już się skończyło. ⏱️', ephemeral=True)
      elif user in sugestia[choice]:
        await interaction.response.send_message('Już zagłosowałeś na tę opcję… 😐', ephemeral=True)
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
    if sugestia.get('annulled', {}).get('time', datetime.now().astimezone()) < sugestia['review_end']:
      review_end = mention_datetime(sugestia['review_end'])
      if 'annulled' in sugestia:
        result = f'Komentowanie miało skończyć się {review_end}. \n'
      else:
        result = f'**Komentowanie jeszcze trwa** i skończy się {review_end}. ❔\n'

    else:
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
      if datetime.now().astimezone() >= sugestia['vote_end']:
        sugestia['outcome'] = len(sugestia['for']) > len(sugestia['against'])
        database.should_save = True

        if sugestia['outcome']:
          logging.info(f'Sugestia {sugestia["id"]} has passed')
        else:
          logging.info(f'Sugestia {sugestia["id"]} did not pass')

  try:
    msg = await bot.get_channel(sugestia['channel']).fetch_message(sugestia['id'])
  except discord.errors.NotFound:
    logging.warn(f'Sugestia {sugestia["id"]} is missing')
    return

  buttonc_before = sum(len(i.children) for i in msg.components)

  await msg.edit(view=view_for(sugestia))

  if is_ongoing(sugestia):
    if buttonc_before < 3 and datetime.now().astimezone() < sugestia['review_end']:
      if config['sugestie_review_ping_role'] is not None:
        await (await msg.channel.send(f'<@&{config["sugestie_review_ping_role"]}>')).delete()
    elif buttonc_before < 4 and datetime.now().astimezone() < sugestia['vote_end']:
      if config['sugestie_vote_ping_role'] is not None:
        await (await msg.channel.send(f'<@&{config["sugestie_vote_ping_role"]}>')).delete()

async def time_updates(sugestia):
  time = sugestia['review_end'] + timedelta(seconds=5) # 5 seconds to make sure the if passes.
  logging.info(f'Waiting until {time} to update sugestia {sugestia["id"]}')
  await sleep_until(time)
  await update(sugestia)

  time = sugestia['vote_end'] + timedelta(seconds=5) # 5 seconds to make sure the if passes.
  logging.info(f'Waiting until {time} to update sugestia {sugestia["id"]}')
  await sleep_until(time)
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

      image, image_format = None, None
      if msg.attachments:
        image_format = msg.attachments[0].content_type
        if image_format is not None and image_format.startswith('image/'):
          image = await msg.attachments[0].read()
        else:
          image_format = None

      await msg.delete()
      if msg.author.bot:
        continue

      embed = discord.Embed(title='Sugestia', description=msg.content)
      embed.set_footer(text=msg.author.our_name, icon_url=msg.author.display_avatar.url)
      if image is None:
        my_msg = await msg.channel.send(embed=embed)
      else:
        filename = 'sugestia' + guess_extension(image_format)
        embed.set_thumbnail(url=f'attachment://{filename}')
        my_msg = await msg.channel.send(embed=embed, file=discord.File(BytesIO(image), filename))

      logging.info(f'{msg.author.id} created sugestia {my_msg.id}')
      sugestia = {
        'id': my_msg.id,
        'channel': my_msg.channel.id,
        'text': msg.content,
        'image': {
          'data': b64encode(image).decode(),
          'format': image_format,
        } if image is not None else None,
        'time': my_msg.created_at,
        'author': msg.author.id,
        'comments': {},
        'review_end': my_msg.created_at + timedelta(seconds=parse_duration(config['sugestie_review_length'])),
        'for': set(),
        'abstain': set(),
        'against': set(),
        'vote_end': my_msg.created_at + timedelta(seconds=parse_duration(config['sugestie_review_length']) + parse_duration(config['sugestie_vote_length'])),
      }
      database.data.setdefault('sugestie', []).append(sugestia)
      database.data['sugestie_clean_until'] = msg.created_at
      database.should_save = True

      await update(sugestia)
      asyncio.create_task(time_updates(sugestia))

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
        asyncio.create_task(time_updates(sugestia))

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
      sugestia = next(i for i in database.data['sugestie'] if i['id'] == int(choice))
      embed = discord.Embed(title=mention_message(bot, sugestia['channel'], sugestia['id']), description=sugestia['text'])
      if sugestia['image'] is None:
        await interaction2.response.send_message(embed=embed, ephemeral=True)
      else:
        filename = 'sugestia' + guess_extension(sugestia['image']['format'])
        embed.set_image(url=f'attachment://{filename}')
        await interaction2.response.send_message(embed=embed, file=discord.File(BytesIO(b64decode(sugestia['image']['data'])), filename), ephemeral=True)

    await interaction.response.send_message('Którą sugestię chcesz zobaczyć?', view=select_view(
      [
        discord.SelectOption(
          label=limit_len(sugestia['text']),
          value=sugestia['id'],
          description=format_datetime(sugestia['time']),
          emoji=emoji_status_of(sugestia),
        )
        for sugestia in reversed(database.data['sugestie'])
      ],
      callback,
      interaction.user,
    ), ephemeral=True)

  @sugestie.command(description='Wyświetla sugestię czekająca na wykonanie')
  @check_pending
  async def pending(interaction):
    async def callback(interaction2, choice):
      sugestia = next(i for i in database.data['sugestie'] if i['id'] == int(choice))
      embed = discord.Embed(title=mention_message(bot, sugestia['channel'], sugestia['id']), description=sugestia['text'])
      if sugestia['image'] is None:
        await interaction2.response.send_message(embed=embed, ephemeral=True)
      else:
        filename = 'sugestia' + guess_extension(sugestia['image']['format'])
        embed.set_image(url=f'attachment://{filename}')
        await interaction2.response.send_message(embed=embed, file=discord.File(BytesIO(b64decode(sugestia['image']['data'])), filename), ephemeral=True)

    await interaction.response.send_message('Którą sugestię chcesz zobaczyć?', view=select_view(
      [
        discord.SelectOption(
          label=limit_len(sugestia['text']),
          value=sugestia['id'],
          description=format_datetime(sugestia['time']),
          emoji=emoji_status_of(sugestia),
        )
        for sugestia in filter(is_pending, reversed(database.data['sugestie']))
      ],
      callback,
      interaction.user,
    ), ephemeral=True)

  @sugestie.command(description='Oznacza sugestię jako wykonaną')
  @check_pending
  @check_staff('wykonywania sugestii')
  async def done(interaction, changes: str):
    async def callback(interaction2, choice):
      sugestia = next(i for i in filter(is_pending, database.data['sugestie']) if i['id'] == int(choice))

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
      [
        discord.SelectOption(
          label=limit_len(sugestia['text']),
          value=sugestia['id'],
          description=format_datetime(sugestia['time']),
        )
        for sugestia in filter(is_pending, reversed(database.data['sugestie']))
      ],
      callback,
      interaction.user,
    ))

  @sugestie.command(description='Unieważnia sugestię')
  @check_annullable
  @check_staff('unieważniania sugestii')
  async def annul(interaction, reason: str):
    async def callback(interaction2, choice):
      sugestia = next(i for i in filter(is_annullable, database.data['sugestie']) if i['id'] == int(choice))

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
      [
        discord.SelectOption(
          label=limit_len(sugestia['text']),
          value=sugestia['id'],
          description=format_datetime(sugestia['time']),
          emoji=emoji_status_of(sugestia),
        )
        for sugestia in filter(is_annullable, reversed(database.data['sugestie']))
      ],
      callback,
      interaction.user,
    ))

  @sugestie.command(description='Usuwa pomyłkowo wysłaną sugestię')
  @check_eraseable
  async def erase(interaction):
    async def callback(interaction2, choice):
      sugestia = next(i for i in filter(is_eraseable_in(interaction2), database.data['sugestie']) if i['id'] == int(choice))

      logging.info(f'{interaction2.user.id} has erased sugestia {sugestia["id"]}')
      database.data['sugestie'].remove(sugestia)

      try:
        await bot.get_channel(sugestia['channel']).get_partial_message(sugestia['id']).delete()
      except discord.errors.NotFound:
        pass

      await interaction.edit_original_response(content=f'Pomyślnie usunięto sugestię o treści `{limit_len(debacktick(sugestia["text"]))}`. 🙄', view=None)
      await interaction2.response.defer()

    await interaction.response.send_message(f'Którą sugestię chcesz usunąć?', view=select_view(
      [
        discord.SelectOption(
          label=limit_len(sugestia['text']),
          value=sugestia['id'],
          description=format_datetime(sugestia['time']),
          emoji=emoji_status_of(sugestia),
        )
        for sugestia in filter(is_eraseable_in(interaction), reversed(database.data['sugestie']))
      ],
      callback,
      interaction.user,
    ))

async def fix_all(from_id):
  logging.info(f'Updating all sugestie starting from {from_id}')
  for sugestia in database.data.get('sugestie', []):
    if sugestia['id'] >= from_id:
      await update(sugestia)
      await update_embed(sugestia)

async def delete_image(id):
  logging.info(f'Deleting image from sugestia {id}')
  sugestia = next(i for i in database.data['sugestie'] if i['id'] == id)
  sugestia['image'] = None
  database.should_save = True
  await update_embed(sugestia)

console.begin('sugestie')
console.register('fix_all', '<id>', 'fixes all sugestie starting from the given one', lambda x: asyncio.run_coroutine_threadsafe(fix_all(int(x)), bot.loop).result())
console.register('delete_image', '<id>', 'deletes the image from a sugestia', lambda x: asyncio.run_coroutine_threadsafe(delete_image(int(x)), bot.loop).result())
console.end()
