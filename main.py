#!/usr/bin/env python3
#
# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023-2025 Karol "digitcrusher" Łacina
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

import discord, sys

import bot, common, console, database
from common import options
from features.reminders import websub

if __name__ == '__main__':
  i = 0
  args = sys.argv[1:]
  while i < len(args):
    if args[i] in {'-c', '--config'}:
      try:
        i += 1
        options['config'] = args[i]
      except IndexError:
        raise Exception(f'Expected a path to config after {args[i - 1]!r}')
    elif args[i] == '--debug':
      options['debug'] = True
    else:
      raise Exception(f'Unknown option: {args[i]!r}')
    i += 1

  discord.utils.setup_logging()
  common.load_config()
  console.start()
  database.start()
  websub.start()

  bot.run()

  # The WebSub server and the database may already have been stopped by the console.
  try:
    websub.stop()
  except:
    pass
  try:
    database.stop()
  except:
    pass
  console.stop()
