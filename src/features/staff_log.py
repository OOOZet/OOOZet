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

import difflib, discord, re
from io import StringIO

from common import config, debacktick, event_listener

# IDEA: log embeds

EMBED_FIELD_LIMIT = 1024

# This function should only be used in combination with _render_content.
def _sanitize_content(message):
  # U+2060 word joiner is used to break up a sequence of 3 backticks. We use only one because we
  # have to fit into the EMBED_FIELD_LIMIT. A second U+2060 at the end is necessary for when there
  # is a sequence of 5 backticks in a row. If the second word joiner is absent, this sequence is
  # escaped like this: '``\u2060```', which is incorrect.
  return message.replace('```', '``\u2060`\u2060').replace('\x1b', '')

def _render_content(content):
  return f'```ansi\n{content}```' if content else ''

def _render_attachments(attachments):
  return '\n'.join(f'- {attachment.url}' for attachment in attachments)

async def log_deleted_message(msg):
  files = []
  embed = discord.Embed(title='Usunięto wiadomość', colour=discord.Colour.red())
  embed.add_field(name='Użytkownik:', value=msg.author.mention)
  embed.add_field(name='Kanał:', value=msg.channel.mention)

  # Longer messages are sent as a ".txt" file. ".md" is not used because Discord also sends messages
  # as a ".txt" file when the user attempts to send a message that is too long. The Markdown
  # renderer for attachments has a slightly different and misleading behaviour from the renderer for
  # messages. Namely, the attachments renderer, for some reason, percent-encodes characters in links
  # that it could not display anyway.
  content = _render_content(_sanitize_content(msg.content))
  if len(content) > EMBED_FIELD_LIMIT:
    files.append(discord.File(StringIO(msg.content), 'Treść.txt'))
  elif content:
    embed.add_field(name='', value=content, inline=False)

  if msg.poll is not None:
    answers = '\n'.join(f'Odpowiedź: `{debacktick(answer.text)}`' for answer in msg.poll.answers)
    embed.add_field(name='Ankieta:', value=f'Pytanie: `{debacktick(msg.poll.question)}`\n{answers}', inline=False)

  if msg.reference is not None:
    embed.add_field(name='Przywołana wiadomość:', value=msg.reference.jump_url, inline=False)

  if len(msg.attachments) == 1:
    embed.set_image(url=msg.attachments[0].url)
  elif msg.attachments:
    embed.add_field(name='Załączniki:', value=_render_attachments(msg.attachments), inline=False)

  await bot.get_channel(config['staff_log_channel']).send(embed=embed, files=files)

@event_listener
async def on_message_delete(msg):
  if msg.author.bot or msg.is_system() or msg.guild is None or msg.guild.id != config['guild']:
    return

  await log_deleted_message(msg)

ANSI_RED = '\x1b[31m'
ANSI_GREEN = '\x1b[32m'
ANSI_CLEAR = '\x1b[0m'

def _highlight_changed_chars(before, after, *, should_return_added, color: str = ANSI_GREEN):
  desired_op = '+' if should_return_added else '-'
  res = ''
  last_op = ' '
  for s in difflib.ndiff(split_on_word_boundaries(before), split_on_word_boundaries(after)):
    op = s[0]
    if op != last_op:
      if op == desired_op:
        res += color
      elif op == ' ':
        res += ANSI_CLEAR
      last_op = op
    if op == desired_op or op == ' ':
      res += s[2:]
  return _render_content(res)

def split_on_word_boundaries(string):
  return re.split(r'(\W+)', string)

@event_listener
async def on_message_edit(before, after):
  if after.author.bot or after.is_system() or after.guild is None or after.guild.id != config['guild']:
    return

  before_content = _sanitize_content(before.content)
  after_content = _sanitize_content(after.content)

  files = []
  embed = discord.Embed(title='Zedytowano wiadomość', colour=discord.Colour.yellow())
  embed.add_field(name='Użytkownik:', value=after.author.mention)
  embed.add_field(name='Wiadomość:', value=after.jump_url)

  if before_content != after_content:
    before_rendered = _highlight_changed_chars(before_content, after_content, should_return_added=False, color=ANSI_RED)
    if len(before_rendered) > EMBED_FIELD_LIMIT:
      files.append(discord.File(StringIO(before.content), 'Przed.txt'))
    else:
      embed.add_field(name='Przed:', value=before_rendered, inline=False)

    after_rendered = _highlight_changed_chars(before_content, after_content, should_return_added=True, color=ANSI_GREEN)
    if len(after_rendered) > EMBED_FIELD_LIMIT:
      files.append(discord.File(StringIO(after.content), 'Po.txt'))
    else:
      embed.add_field(name='Po:', value=after_rendered, inline=False)

  if before.reference != after.reference:
    embed.add_field(name='Przywołana wiadomość przed:', value=before.reference.jump_url, inline=False)
    embed.add_field(name='Przywołana wiadomość po:', value=after.reference.jump_url, inline=False)

  if before.attachments != after.attachments:
    embed.add_field(name='Załączniki przed:', value=_render_attachments(before.attachments), inline=False)
    embed.add_field(name='Załączniki po:', value=_render_attachments(after.attachments), inline=False)

  await bot.get_channel(config['staff_log_channel']).send(embed=embed, files=files)

@event_listener
async def on_member_update(before, after):
  if before.display_name == after.display_name:
    return

  embed = discord.Embed(title='Zmieniono nick użytkownika', colour=discord.Colour.yellow())
  embed.add_field(name='Użytkownik:', value=after.mention)
  embed.add_field(name='Przed:', value=f'`{debacktick(before.display_name)}`', inline=False)
  embed.add_field(name='Po:', value=f'`{debacktick(after.display_name)}`', inline=False)
  await bot.get_channel(config['staff_log_channel']).send(embed=embed)
