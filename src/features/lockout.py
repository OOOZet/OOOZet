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

import aiohttp, asyncio, discord, random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from discord import app_commands
from math import ceil

import console, database
from common import config, event_listener, log_exceptions, loop, mention_datetime, parse_duration, sleep_until
from features.codeforces_handles import get_handle

lock = asyncio.Lock()
problemset = {}
filtered_problemset = {}
invites = []

async def can_message(user):
  try:
    await user.send()
  except discord.Forbidden:
    return False
  except:
    return True
  assert False

class InviteSelfError(app_commands.CheckFailure):
  pass

class NoCodeforcesHandleBothError(app_commands.CheckFailure):
  pass

@dataclass
class NoCodeforcesHandleError(app_commands.CheckFailure):
  user: discord.User

class SendingMultipleInvitesError(app_commands.CheckFailure):
  pass

class InvitingWhileInDuelError(app_commands.CheckFailure):
  pass

@dataclass
class CannotMessageError(app_commands.CheckFailure):
  user: discord.User

def check_invite_preconditions(interaction, invitee):
  if interaction.user == invitee:
    raise InviteSelfError()
  elif get_handle(interaction.user.id) is None and get_handle(invitee.id) is None:
    raise NoCodeforcesHandleBothError()
  elif get_handle(interaction.user.id) is None:
    raise NoCodeforcesHandleError(interaction.user)
  elif get_handle(invitee.id) is None:
    raise NoCodeforcesHandleError(invitee)
  elif any(invite.inviter == interaction.user for invite in invites):
    raise SendingMultipleInvitesError()
  elif any(interaction.created_at < duel['end'] for duel in database.data.get('lockout_duels', []) if interaction.user.id in duel['players']):
    raise InvitingWhileInDuelError()
  # We don't check if the recipient is in any ongoing duel because that would be a breach of privacy.

async def check_messageabilty(interaction, invitee):
  if not await can_message(interaction.user):
    raise CannotMessageError(interaction.user)
  elif not await can_message(invitee):
    raise CannotMessageError(invitee)

def problem_id(json):
  return f'{json["contestId"]}/{json["index"]}'

def problem_id_to_url(i):
  return f'https://codeforces.com/problemset/problem/{i}'

def duel_results(duel):
  results = [0] * len(duel['players'])
  for task in duel['tasks']:
    if 'solved' in task:
      results[task['solved_by']] += task['value']
  return sorted(enumerate(results), key=lambda x: x[1], reverse=True)

def duel_winner(duel):
  results = duel_results(duel)
  return results[0][0] if all(score < results[0][1] for i, score in results[1:]) and 'aborted' not in duel else None

def duel_view(duel):
  async def on_refresh(interaction):
    if 'last_update' in duel:
      now = datetime.now().astimezone()
      time = duel['last_update'] + timedelta(seconds=parse_duration(config['lockout_refresh_cooldown']))
      if now < time:
        await interaction.response.send_message(
          f'Widok pojedynku był już niedawno odświeżony. Spróbuj ponownie {mention_datetime(time, relative=True)}. ⏱️',
          ephemeral=True,
        )
        return
    duel['last_update'] = datetime.now().astimezone()

    log.info(f'{interaction.user.id} requested to update duel between {duel["players"]}')
    await interaction.response.defer(thinking=True, ephemeral=True)
    await update_duel(duel)
    await interaction.delete_original_response()

  async def on_abort(interaction):
    if interaction.created_at >= duel['end']:
      await interaction.response.send_message('Ten pojedynek już się zakończył… 🤨', ephemeral=True)
      return

    log.info(f'{interaction.user.id} aborted lockout duel between {duel["players"]}')
    duel['aborted'] = duel['players'].index(interaction.user.id)
    duel['end'] = interaction.created_at
    database.data['lockout_duels'].remove(duel)
    database.should_save = True
    await update_duel(duel)

  if 'last_update' in duel and duel['last_update'] >= duel['end']:
    return None

  view = discord.ui.View(timeout=None)

  refresh = discord.ui.Button(custom_id='refresh', label='Odśwież', style=discord.ButtonStyle.blurple)
  refresh.callback = on_refresh
  view.add_item(refresh)

  if not any('solved' in task for task in duel['tasks']):
    abort = discord.ui.Button(custom_id='abort', label='Przerwij', style=discord.ButtonStyle.red)
    abort.callback = on_abort
    async def interaction_check(interaction):
      return interaction.user.id in duel['players']
    abort.interaction_check = interaction_check
    view.add_item(abort)

  return view

def duel_msg_content(duel):
  players = ' vs '.join(f'<@{i}>' for i in duel['players'])
  result = f'## Lockout {players} ⚔️\n'

  for task in duel['tasks']:
    name = problemset[task['id']]['name']
    url = problem_id_to_url(task['id'])
    if 'solved' in task:
      name = f'~~{name}~~'
    result += f'- [{name}]({url}) warte **{task["value"]}** punktów'
    if 'solved' in task:
      solver = duel['players'][task['solved_by']]
      penalty = (task['solved'] - duel['start']).total_seconds()
      result += f' rozwiązane przez <@{solver}> w **{penalty // 60:.0f}:{penalty % 60:02.0f}**'
    result += '\n'

  if 'last_update' not in duel or duel['last_update'] < duel['end']:
    result += '**Bieżące wyniki:** 🏆\n'
    for i, score in duel_results(duel):
      result += f'{i + 1}. <@{duel["players"][i]}> z **{score}** punktami\n'
    result += f'Koniec pojedynku {mention_datetime(duel["end"], relative=True)}. ⏱️\n'
  elif 'aborted' in duel:
    result += f'Pojedynek został **przerwany** przez <@{duel["players"][duel["aborted"]]}>. 🛑\n'
  elif (winner := duel_winner(duel)) is not None:
    result += f'Pojedynek **wygrał** <@{duel["players"][winner]}>! 🥇\n'
  else:
    result += 'Pojedynek zakończył się **remisem**. 🤝\n'

  return result

async def get_duel_players_submissions(duel):
  async with aiohttp.ClientSession('https://codeforces.com/api/') as session:
    async def get(user):
      return await (await session.get('user.status', params={'handle': get_handle(user)})).json()
    result = await asyncio.gather(*(get(i) for i in duel['players']))
  for json in result:
    if json['status'] != 'OK':
      raise Exception(f'Codeforces user submissions request failed: {json["comment"]!r}')
  return result

# HACK: how to handle AC submissions from before the duel started?
async def update_duel(duel):
  log.info(f'Updating lockout duel between {duel["players"]}')
  duel['last_update'] = datetime.now().astimezone()

  try:
    if 'aborted' not in duel:
      duel['end'] = duel['start'] + timedelta(seconds=duel['settings']['duration'])

    first_solves = {}
    for player, player_submissions in enumerate(await get_duel_players_submissions(duel)):
      for submission in player_submissions['result']:
        if submission['verdict'] != 'OK':
          continue
        time = datetime.fromtimestamp(submission['creationTimeSeconds'], timezone.utc)
        if time > duel['end']:
          continue
        i = problem_id(submission['problem'])
        if i not in first_solves or time < first_solves[i][0]:
          first_solves[i] = (time, player)

    for task in duel['tasks']:
      if task['id'] in first_solves:
        task['solved'], task['solved_by'] = first_solves[task['id']]
      else:
        try:
          del task['solved']
          del task['solved_by']
        except KeyError:
          pass

    if all('solved' in task for task in duel['tasks']):
      duel['end'] = max(duel['start'], *(task['solved'] for task in duel['tasks']))

    database.should_save = True

    msg_content = duel_msg_content(duel)
    view = duel_view(duel)
    for chan, msg in duel['messages']:
      await (await bot.fetch_channel(chan)).get_partial_message(msg).edit(content=msg_content, view=view)

  except:
    del duel['last_update']
    database.should_save = True
    raise

@log_exceptions
async def time_duel_update(duel):
  time = duel['end'] + timedelta(seconds=5) # 5 seconds to make sure the if passes.
  log.info(f'Waiting until {time} to update lockout duel between {duel["players"]}')
  await sleep_until(time)
  await update_duel(duel)

class Invite:
  def __init__(self, interaction, invitee, settings):
    self.interaction = interaction
    self.invitee = invitee
    self.settings = settings
    self.msg = None
    self.duel = None

  @property
  def inviter(self):
    return self.interaction.user

  @property
  def time(self):
    return self.interaction.created_at

  @property
  def timeout(self):
    return parse_duration(config['lockout_invite_timeout'])

  @property
  def timeout_time(self):
    return min(self.time + timedelta(seconds=self.timeout), self.interaction.expires_at)

  async def finish_interaction(self):
    async with lock:
      check_invite_preconditions(self.interaction, self.invitee)
      log.info(f'{self.inviter.id} challenged {self.invitee.id} to a lockout duel')
      invites.append(self)

    try:
      minutes = ceil(self.settings['duration'] / 60)
      timeout_time = mention_datetime(self.timeout_time, relative=True)
      view = self.view
      try:
        self.msg = await self.invitee.send(
          f'{self.inviter.mention} wyzywa cię na {minutes}-minutowy pojedynek w **lockout**! To zaproszenie wygasa {timeout_time}. ⚔️',
          view=view,
          suppress_embeds=True,
        )
      except discord.Forbidden:
        invites.remove(self)
        raise CannotMessageError(self.invitee)

      await self.interaction.response.send_message(f'Pomyślnie wysłano zaproszenie do {self.invitee.mention}, które wygaśnie {timeout_time}. 🥳', ephemeral=True)

      asyncio.create_task(self.time_update())

    except:
      invites.remove(self)
      try:
        await self.msg.delete()
      except:
        pass
      raise

  @property
  def view(self):
    accept = discord.ui.Button(custom_id='accept', label='Przyjmij wyzwanie', style=discord.ButtonStyle.green)
    accept.callback = self.accept
    view = discord.ui.View(timeout=self.timeout)
    view.add_item(accept)
    return view

  # We allow a player to accept multiple duels at a time for extra fun.
  async def accept(self, interaction):
    log.info(f'{self.invitee.id} accepted lockout duel from {self.inviter.id}')
    await interaction.response.defer(thinking=True, ephemeral=True)

    duel = {
      'players': [self.inviter.id, self.invitee.id],
      'settings': self.settings,
    }

    submissions = await get_duel_players_submissions(duel)
    solved_problems = {problem_id(submission['problem']) for json in submissions for submission in json['result'] if submission['verdict'] == 'OK'}
    filtered_problems = {k for k, v in filtered_problemset.items() if duel['settings']['min_rating'] <= v['rating'] <= duel['settings']['max_rating']}

    population = list(filtered_problems - solved_problems)
    count = duel['settings']['taskc']
    try:
      chosen_ids = random.sample(population, count)
    except ValueError:
      await interaction.response.send_message('Nie znalazłem wystarczająco zadań, które spełniałyby podane kryteria i których żadne z was nie rozwiązało… 🧐', ephemeral=True)
      return
    duel['tasks'] = [
      {
        'id': i,
        'value': problemset[i]['rating'],
      }
      for i in chosen_ids
    ]

    try:
      try:
        msg_to_inviter = await self.inviter.send(f'Twój pojedynek z {self.invitee.mention} wkrótce się rozpocznie… ⌛', suppress_embeds=True)
      except discord.Forbidden:
        raise CannotMessageError(self.inviter)

      duel['start'] = datetime.now().astimezone()
      duel['messages'] = [[msg_to_inviter.channel.id, msg_to_inviter.id], [self.msg.channel.id, self.msg.id]]

      await update_duel(duel)
      asyncio.create_task(time_duel_update(duel))

    except:
      try:
        await msg_to_inviter.delete()
      except:
        pass
      raise

    # At this point the original invite message has already been overwritten by
    # update_duel, so there is no point in doing error recovery for the next steps.
    invites.remove(self)
    assert self.duel is None
    self.duel = duel
    database.data.setdefault('lockout_duels', []).append(duel)
    database.should_save = True

    await self.interaction.edit_original_response(content=f'{self.invitee.mention} przyjął twoje wyzwanie! **Kliknij [tutaj]({msg_to_inviter.jump_url})** aby przejść do wiadomości z widokiem pojedynku. 👀')
    await interaction.delete_original_response()

  @log_exceptions
  async def time_update(self):
    time = self.timeout_time + timedelta(seconds=5) # 5 seconds to make sure the if passes.
    log.info(f'Waiting until {time} to update lockout invite from {self.inviter.id} to {self.invitee.id}')
    await sleep_until(time)
    await self.update()

  async def update(self):
    if self.duel is not None:
      return

    log.info(f'Updating lockout invite from {self.inviter.id} to {self.invitee.id}')
    if datetime.now().astimezone() >= self.timeout_time:
      invites.remove(self)
      await self.interaction.edit_original_response(content=f'{self.invitee.mention} nie przyjął twojego wyzwania… 😔')
      await self.msg.edit(view=None)

@event_listener
async def on_check_failure(interaction, error):
  match error:
    case InviteSelfError():
      await interaction.response.send_message('Nie możesz pojedynkować się z samym sobą… 🤨', ephemeral=True)
    case NoCodeforcesHandleBothError():
      await interaction.response.send_message('Oboje musicie podać mi swój nick na Codeforces za pomocą komendy `/codeforces set`, żeby móc zagrać w lockout. 😊', ephemeral=True)
    case NoCodeforcesHandleError(user):
      if user == interaction.user:
        await interaction.response.send_message('Musisz podać mi swój nick na Codeforces za pomocą komendy `/codeforces set`, żeby móc zagrać w lockout. 😊', ephemeral=True)
      else:
        await interaction.response.send_message(f'{user.mention} musi podać mi swój nick na Codeforces za pomocą komendy `/codeforces set`, żeby móc zagrać w lockout. 😊', ephemeral=True)
    case SendingMultipleInvitesError():
      await interaction.response.send_message('Nie możesz wyzywać na pojedynek wielu użytkowników na raz. 🤨', ephemeral=True)
    case InvitingWhileInDuelError():
      await interaction.response.send_message('Nie możesz wyzywać innych na pojedynek, gdy już jesteś w jednym pojedynku. 😐', ephemeral=True)
    case CannotMessageError(user):
      if user == interaction.user:
        await interaction.response.send_message('Nie mogę wysłać wiadomości do ciebie. Sprawdź swoje ustawienia otrzymywania wiadomości prywatnych od innych. 🥺', ephemeral=True)
      else:
        await interaction.response.send_message(f'Nie mogę wysłać wiadomości do {user.mention}. Poproś go o sprawdzenie swoich ustawień otrzymywania wiadomości prywatnych od innych. 🥺', ephemeral=True)
    case _:
      raise

@event_listener
async def on_ready():
  for duel in database.data.get('lockout_duels', []):
    view = duel_view(duel)
    if view is not None:
      for chan, msg in duel['messages']:
        bot.add_view(view, message_id=msg)
    if 'last_update' not in duel or duel['last_update'] <= duel['end']:
      asyncio.create_task(time_duel_update(duel))
  log.info('Lockout is ready')

lockout = app_commands.Group(name='lockout', description='Komendy do lockouta')

async def challenge(interaction, user):
  check_invite_preconditions(interaction, user)
  await check_messageabilty(interaction, user)

  async def on_submit(interaction2):
    settings = {
      'taskc': int(taskc.values[0]),
      'duration': parse_duration(duration.values[0]),
    }
    try:
      settings['min_rating'] = int(min_rating.value)
      settings['max_rating'] = int(max_rating.value)
    except ValueError:
      await interaction2.response.send_message('Trudność zadania musi być liczbą… 🤨', ephemeral=True)
      return
    if settings['min_rating'] > settings['max_rating']:
      await interaction2.response.send_message('Przedział trudności zadań nie może być pusty… 😐', ephemeral=True)
      return

    await Invite(interaction2, user, settings).finish_interaction()

  taskc = discord.ui.Select()
  for count in config['lockout_taskc_choices']:
    taskc.add_option(label=count, value=count)
  duration = discord.ui.Select()
  for label, value in config['lockout_duration_choices']:
    duration.add_option(label=label, value=value)
  min_rating = discord.ui.TextInput(default=config['lockout_min_rating_default'], max_length=4)
  max_rating = discord.ui.TextInput(default=config['lockout_max_rating_default'], max_length=4)

  modal = discord.ui.Modal(title=f'Wyzwij {user} na pojedynek w lockout')
  modal.on_submit = on_submit
  modal.add_item(discord.ui.TextDisplay(
    'Lockout to gra dwuosobowa, w której obaj gracze dostają do rozwiązania '
    'na czas losowy zestaw zadań z Codeforces. Punkty za zadanie dostaje '
    'ten, który rozwiązał je jako pierwszy.',
  ))
  modal.add_item(discord.ui.Label(text='Liczba zadań', component=taskc))
  modal.add_item(discord.ui.Label(text='Czas trwania pojedynku', component=duration))
  modal.add_item(discord.ui.Label(text='Minimalna trudność zadań', component=min_rating))
  modal.add_item(discord.ui.Label(text='Maksymalna trudność zadań', component=max_rating))
  await interaction.response.send_modal(modal)

@lockout.command(name='challenge', description='Wyzywa na pojedynek w lockout')
async def cmd_challenge(interaction, user: discord.User):
  await challenge(interaction, user)

@app_commands.context_menu(name='Zagraj w lockout')
async def menu_challenge(interaction, user: discord.User):
  await challenge(interaction, user)

@loop(interval=config['codeforces_problemset_poll_rate'])
async def poll():
  log.info('Periodically downloading Codeforces problemset and contest list')

  async with aiohttp.ClientSession('https://codeforces.com/api/') as session:
    json = await (await session.get('problemset.problems')).json()
    contests = await (await session.get('contest.list')).json() # HACK: we probably shouldn't duplicate this with reminders.codeforces
  if json['status'] != 'OK':
    log.error(f'Codeforces problemset request failed: {json["comment"]!r}')
    return
  if contests['status'] != 'OK':
    log.error(f'Codeforces contest list request failed: {contests["comment"]!r}')
    return

  global filtered_problemset, problemset
  new = {}
  for i in json['result']['problems']:
    new.setdefault(problem_id(i), {}).update(i)
  for i in json['result']['problemStatistics']:
    new.setdefault(problem_id(i), {}).update(i)
  problemset = new
  contests = {contest['id']: contest for contest in contests['result']}
  filtered_problemset = {
    i: problem
    for i, problem in new.items()
    if 'rating' in problem and any(keyword in contests[problem['contestId']]['name'] for keyword in config['lockout_contest_whitelist'])
  }

@console.operation(desc='lists all active duels and invites')
def status():
  result = ''
  for invite in invites:
    result += f'invite from {invite.inviter.id} to {invite.invitee.id} expires {invite.timeout_time}\n'
  for duel in database.data.get('lockout_duels', []):
    if datetime.now().astimezone() < duel['end']:
      result += f'duel between {duel["players"]} ends {duel["end"]}\n'
  if not result:
    result = 'no active duels nor invites'
  return result

@console.operation(name='update-duel', desc='updates duel by index')
async def op_update_duel(idx: int):
  await update_duel(database.data['lockout_duels'][idx])
