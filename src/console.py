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

import asyncio, inspect, json, pprint, socket, threading, time, traceback
from dataclasses import dataclass
from logging import getLogger
from typing import Callable, Optional

import common
from common import config, parse_duration, redacted_config

log = getLogger(__name__)

async_loop = None
server = None
thread = None
should_stop_listen = False
should_stop_conn = False

def start():
  global server
  server = socket.socket()
  server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  # This connection has absolutely no authentication and should never be exposed to the
  # Internet directly. If you really want to access it remotely, then use an SSH tunnel.
  host = '127.0.0.1'
  server.bind((host, config['console_port']))
  server.listen(1)

  global thread
  thread = threading.Thread(target=listen)
  thread.start()

  log.info(f'Started console on {host}:{config["console_port"]}')

def stop():
  log.info('Stopping console')

  global should_stop_listen, should_stop_conn
  should_stop_listen = True
  should_stop_conn = True

  if client is not None:
    # This will cancel a pending client.recv(). We can still send data to the
    # client after this because this closes the socket only for incoming data.
    client.shutdown(socket.SHUT_RD)
  server.shutdown(socket.SHUT_RDWR) # This will cancel a pending server.accept().
  if threading.current_thread() != thread: # console.restart also uses this function and we obviously can't thread.join() ourselves there.
    thread.join()
  server.close()

client = None

# TODO: do we really want to play cat and mouse with all these specific exceptions?
def listen():
  global should_stop_listen
  should_stop_listen = False
  while not should_stop_listen:
    try:
      global client
      (client, addr) = server.accept()
    except OSError:
      continue # We probably got cancelled by stop().

    log.info(f'Console accepted connection from {addr[0]}:{addr[1]}')
    try:
      client.send(f'{config["console_hello"]} says hello!\n'.encode())
      client.send('Type "help" to get a list of available operations.\n'.encode())
    except BrokenPipeError:
      pass

    is_client_gone = False

    global should_stop_conn
    should_stop_conn = False
    while not should_stop_conn:
      try:
        client.send(b'> ')
      except BrokenPipeError:
        pass

      timeout = parse_duration(config['console_timeout'])
      client.settimeout(timeout)
      try:
        chunk = client.recv(4096)
      except TimeoutError:
        client.send(f'\nTimed out after {timeout} seconds.\n'.encode())
        break

      if not chunk:
        if should_stop_listen: # This is how we know we got cancelled by stop().
          client.send(b'\nI have to go, bye.\n')
        else:
          is_client_gone = True
          try:
            client.send(b'\nThe connection got closed without a goodbye. How rude!\n')
          except BrokenPipeError:
            pass
        break
      elif chunk == b'\x04':
        client.send(b'\nGot end of transmission without a goodbye. How rude!\n')
        break

      line = bytearray(chunk)
      client.setblocking(False)
      try:
        while chunk := client.recv(4096):
          line += chunk
      except BlockingIOError: # There is nothing left to receive.
        pass

      try:
        line = line.decode()
      except Exception as e:
        log.exception('Got exception while decoding console command')
        try:
          client.send(''.join(traceback.format_exception(None, e, e.__traceback__)).encode())
        except BrokenPipeError: # The client sent junk and ran away.
          pass
        continue

      log.info(f'Console received command {line!r}')

      try:
        reply = run(line)
        if reply is not None and not isinstance(reply, str):
          reply = pprint.pformat(reply, sort_dicts=False)
      except Exception as e:
        log.exception('Got exception while running console command')
        reply = ''.join(traceback.format_exception(None, e, e.__traceback__))

      try:
        if reply is not None:
          client.send(reply.encode())
          if not reply.endswith('\n'):
            client.send(b'\n')
      except BrokenPipeError: # The client sent a command and ran away.
        pass

    try: # We don't want any exceptions here because that would kill our thread and the whole console.
      if not is_client_gone: # Calling shutdown() on a socket closed by the client would raise an exception.
        client.shutdown(socket.SHUT_RDWR)
      client.close()
    except:
      log.exception('Got exception while closing console connection')
    client = None
    log.info('Console connection closed')

def operation(*args, **kwargs):
  def decorator(func):
    return Operation(func, *args, **kwargs)
  return decorator

class Operation:
  def __init__(self, func, *, scope=None, name=None, params=None, desc=None, should_split_args=True):
    self.func = func
    self.scope = scope
    self.name = func.__name__.strip('_').replace('_', '-') if name is None else name
    if params is None:
      params = []
      for i in inspect.signature(func).parameters.values():
        name = i.name.strip('_').replace('_', '-')
        if i.kind == i.VAR_POSITIONAL:
          params.append(f'[{name}...]')
        elif i.kind in {i.POSITIONAL_ONLY, i.POSITIONAL_OR_KEYWORD}:
          if i.default is i.empty:
            params.append(f'<{name}>')
          else:
            params.append(f'[{name}]')
        else:
          assert i.kind in {i.KEYWORD_ONLY, i.VAR_KEYWORD}, i
      params = ' '.join(params) if params else None
    self.params = params
    self.desc = desc
    self.should_split_args = should_split_args

  @property
  def scope(self):
    return '.'.join(self.scope_parts) if self.scope_parts else None

  @scope.setter
  def scope(self, value):
    self.scope_parts = [] if value is None else value.split('.')

  @property
  def scoped_name(self):
    return '.'.join(self.scope_parts + [self.name])

  def __call__(self, *args, **kwargs):
    return self.func(*args, **kwargs)

operations = []

def run(cmd):
  cmd = cmd.strip()
  if not cmd:
    return

  name, _, arg = cmd.partition(' ')
  if arg is not None:
    arg = arg.lstrip()

  for op in operations:
    assert all(map(is_identifier, op.scope_parts)) and is_identifier(op.name), op.scoped_name
    if name != op.scoped_name:
      continue

    if arg is None:
      args = []
    elif op.should_split_args:
      args = arg.split()
    else:
      args = [arg]
    params = [i for i in inspect.signature(op.func).parameters.values() if i.kind not in {i.KEYWORD_ONLY, i.VAR_KEYWORD}]
    is_vararg = params and params[-1].kind == params[-1].VAR_POSITIONAL
    for i in range(len(args) if is_vararg else min(len(args), len(params))):
      cls = params[min(i, len(params) - 1)].annotation
      if cls is int:
        args[i] = int(args[i])
      else:
        assert cls is str, (op.scoped_name, i)

    result = op(*args)
    if asyncio.iscoroutine(result):
      return asyncio.run_coroutine_threadsafe(result, async_loop).result()
    else:
      return result

  raise Exception(f'Unknown operation: {name!r}')

def is_identifier(string):
  return string and '.' not in string and not any(map(str.isspace, string)) and string.isprintable()

def register(*ops):
  for op in ops:
    assert op not in operations
    operations.append(op)

@operation(name='help', desc='prints this help message')
def op_help():
  lines = []
  max_a_width = 0
  for op in operations:
    a = '  ' + op.scoped_name
    if op.params is not None:
      a += ' ' + op.params
    lines.append((a, op.desc))
    max_a_width = max(max_a_width, len(a))

  result = 'Operations:\n'
  for a, b in lines:
    result += a.ljust(max_a_width + 2) + b + '\n'
  return result

@operation(name='bye', desc='closes this connection')
def op_bye():
  global should_stop_conn
  should_stop_conn = True
  return 'Goodbye!'

@operation(name='restart', desc='restarts the console')
def op_restart():
  stop()
  # We have to delay the start() because otherwise it would override client and
  # should_stop_listen and we wouldn't be able to properly clean up and return
  # from listen().
  def target():
    while client is not None:
      time.sleep(0.1)
    start()
  delayed_start = threading.Thread(target=target)
  delayed_start.start()
  return 'Restarting the console...'

@operation(scope='config', name='all', desc='prints the config')
def op_all():
  return redacted_config()

@operation(scope='config', name='get', desc='prints the value of config key')
def op_get(key: str):
  return redacted_config()[key]

@operation(scope='config', name='set', params='<key> <json value>', desc='sets config key to value', should_split_args=False)
def op_set(arg: str):
  key, _, value = arg.partition(' ')
  config[key] = json.loads(value)

@operation(scope='config', name='load', desc='loads the config from file')
def op_load():
  common.load_config()

@operation(scope='config', name='save', desc='saves the config to file')
def op_save():
  common.save_config()

register(op_help, op_bye, op_restart, op_all, op_get, op_set, op_load, op_save)
