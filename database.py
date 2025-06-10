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

import json, logging, os, shutil, threading
from datetime import date, datetime

import console
from common import config, parse_duration

data = None
should_save = False
lock = threading.RLock()

def load():
  logging.info('Loading database')
  with lock:
    try:
      def object_hook(object):
        if set(object) == {'__set__'}:
          return set(object['__set__'])
        elif set(object) == {'__datetime__'}:
          return datetime.fromisoformat(object['__datetime__'])
        else:
          def maybe_int(x):
            try:
              return int(x)
            except ValueError:
              return x
          return {maybe_int(k): v for k, v in object.items()}
      with open(config['database'], 'r') as file:
        global data
        data = json.load(file, object_hook=object_hook)
    except FileNotFoundError:
      data = {}
    global should_save
    should_save = False

def save():
  logging.info('Saving database')
  with lock:
    assert data is not None
    global should_save
    should_save = False

    class Encoder(json.JSONEncoder):
      def default(self, value):
        if isinstance(value, set):
          return {'__set__': list(value)}
        elif isinstance(value, datetime):
          return {'__datetime__': value.isoformat()}
        else:
          return super().default(value)
    # This is not an atomic disk operation, so if we were to save directly to
    # database.json, then there could be a power outage and we would end up
    # having a truncated database to load on next boot.
    with open(config['database'] + '.new', 'w') as file:
      json.dump(data, file, cls=Encoder)
    try:
      shutil.copy2(config['database'], config['database'] + '.' + date.today().isoformat())
    except FileNotFoundError:
      pass
    os.replace(config['database'] + '.new', config['database'])

autosave_thread = None
autosave_stop = None

def start():
  global autosave_thread, autosave_stop
  if autosave_thread is not None or autosave_stop is not None:
    raise Exception('The database is already started')
  logging.info('Starting database')

  load()

  autosave_stop = threading.Event()
  def autosave():
    autosave_stop.clear()
    while not autosave_stop.is_set():
      autosave_stop.wait(timeout=parse_duration(config['autosave']))
      if should_save:
        save()
  autosave_thread = threading.Thread(target=autosave)
  autosave_thread.start()

def stop():
  global autosave_thread, autosave_stop
  if autosave_thread is None or autosave_stop is None:
    raise Exception('The database is already stopped')
  logging.info('Stopping database')

  autosave_stop.set()
  autosave_thread.join()
  autosave_stop = None
  autosave_thread = None

console.begin('database')
console.register('data',  None, 'prints the database',          lambda: data)
console.register('load',  None, 'loads the database from file', load)
console.register('save',  None, 'saves the database to file',   save)
console.register('start', None, 'starts the database',          start)
console.register('stop',  None, 'stops the database',           stop)
console.end()
