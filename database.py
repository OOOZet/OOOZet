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

import json, logging, os, threading

import console
from common import config, parse_duration

data = {}
should_save = False
lock = threading.RLock()

def load():
  logging.info('Loading database')
  with lock:
    try:
      def object_hook(object):
        if '__set__' in object:
          result = set()
          for item in object:
            if item != '__set__':
              try:
                result.add(int(item))
              except ValueError:
                result.add(item)
          return result
        else:
          result = {}
          for key, value in object.items():
            try:
              result[int(key)] = value
            except ValueError:
              result[key] = value
          return result
      with open(config['database'], 'r') as file:
        loaded = json.load(file, object_hook=object_hook)

      global data, should_save
      data |= loaded
      should_save = False
    except FileNotFoundError:
      pass

def save():
  logging.info('Saving database')
  with lock:
    if os.path.exists(config['database']):
      os.replace(config['database'], config['database'] + '.old')

    class Encoder(json.JSONEncoder):
      def default(self, value):
        if isinstance(value, set):
          result = {'__set__': True}
          for item in value:
            result[item] = None
          return result
        return json.JSONEncoder.default(self, value)
    with open(config['database'], 'x') as file:
      json.dump(data, file, cls=Encoder)

    global should_save
    should_save = False

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
