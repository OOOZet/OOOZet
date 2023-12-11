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

import json, logging, pprint, socket, threading, time, traceback
from dataclasses import dataclass
from typing import Callable, Optional

import common
from common import config, parse_duration, redacted_config

server = None
thread = None
should_stop_listen = False
should_stop_conn = False

def start():
  global server
  server = socket.socket()
  server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  server.bind((config['console_host'], config['console_port']))
  server.listen(1)

  global thread
  thread = threading.Thread(target=listen)
  thread.start()

  logging.info(f'Started console on {config["console_host"]}:{config["console_port"]}')

def stop():
  logging.info('Stopping console')

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

def listen():
  global should_stop_listen
  should_stop_listen = False
  while not should_stop_listen:
    try:
      global client
      (client, addr) = server.accept()
    except OSError:
      continue # We probably got cancelled by stop().

    logging.info(f'Console accepted connection from {addr[0]}:{addr[1]}')
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
        logging.exception('Got exception while decoding console command')
        client.send(''.join(traceback.format_exception(None, e, e.__traceback__)).encode())
        continue

      logging.info(f'Console received command {repr(line)}')

      try:
        reply = run(line)
        if reply is not None and not isinstance(reply, str):
          reply = pprint.pformat(reply, sort_dicts=False)
      except Exception as e:
        logging.exception('Got exception while running console command')
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
      logging.exception('Got exception while closing console connection')
    client = None
    logging.info('Console connection closed')

@dataclass
class Operation:
  scope: list[str]
  names: list[str]
  params: str | None
  desc: str
  func: Callable[[str], Optional[any]]

operations = []

def run(cmd):
  cmd = cmd.strip()
  if not cmd:
    return

  if ' ' in cmd:
    name, _, arg = cmd.partition(' ')
    arg = arg.lstrip()
  else:
    name = cmd
    arg = ''

  for op in operations:
    if name in ('.'.join(op.scope + [name]) for name in op.names):
      if op.params is not None:
        return op.func(arg)
      elif arg:
        raise Exception(f'Operation {repr(name)} expects no arguments')
      else:
        return op.func()
  raise Exception(f'Unknown operation: {repr(name)}')

scope = []

def begin(name):
  scope.append(name)

def end():
  scope.pop()

def register(names, params, desc, func):
  if not isinstance(names, list):
    names = [names]
  operations.append(Operation(scope.copy(), names, params, desc, func))

def op_help():
  lines = []
  max_a_width = 0
  for op in operations:
    a = '  '
    for name in op.scope:
      a += name + '.'

    if len(op.names) <= 1:
      a += op.names[0]
    else:
      if op.scope:
        a += '{'
      a += ', '.join(op.names)
      if op.scope:
        a += '}'

    if op.params is not None:
      a += ' ' + op.params

    lines.append((a, op.desc))
    max_a_width = max(max_a_width, len(a))

  result = 'Operations:\n'
  for a, b in lines:
    result += a.ljust(max_a_width + 2) + b + '\n'
  return result

def op_bye():
  global should_stop_conn
  should_stop_conn = True
  return 'Goodbye!'

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

register('help',    None, 'prints this help message', op_help)
register('bye',     None, 'closes this connection',   op_bye)
register('restart', None, 'restarts the console',     op_restart)

def op_set(arg):
  key, _, value = arg.partition(' ')
  config[key] = json.loads(value)

begin('config')
register('all',  None,                 'prints the config',              lambda: redacted_config())
register('get',  '<key>',              'prints the value of config key', lambda arg: redacted_config()[arg])
register('set',  '<key> <json value>', 'sets config key to value',       op_set)
register('load', None,                 'loads the config from file',     common.load_config)
register('save', None,                 'saves the config to file',       common.save_config)
end()
