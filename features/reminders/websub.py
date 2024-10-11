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

import hmac, http.server, itertools, logging, requests, threading, time
from concurrent.futures import Future
from math import ceil
from secrets import token_urlsafe
from urllib.parse import parse_qsl, urlparse

import console
from common import config, parse_duration

on_msg = None # Override this.

server = None

def start():
  logging.info('Starting WebSub server')

  global server
  server = Server()
  server.async_serve_forever()
  server.subscribe()

def stop():
  logging.info('Stopping WebSub server')

  global server
  server.unsubscribe().result()
  server.shutdown()
  server = None

class Server(http.server.HTTPServer):
  def __init__(self):
    super().__init__(('0.0.0.0', config['websub_port']), HttpRequestHandler)

    self.hub = 'https://pubsubhubbub.appspot.com/'
    self.topic = f'https://www.youtube.com/xml/feeds/videos.xml?channel_id={config["oki_youtube"]}' # The official documentation is wrong about this.

    self.callback = f'http://{config["websub_host"]}:{config["websub_port"]}/{token_urlsafe()}'
    self.secret = token_urlsafe() # Some hubs fail with token_bytes.
    self.should_be_subbed = False
    self.verification_event = threading.Event()

  def async_serve_forever(self):
    threading.Thread(target=self.serve_forever).start()

  def subscribe(self):
    self.should_be_subbed = True
    return self.async_sub(config['websub_sub_retries'])

  def unsubscribe(self):
    self.should_be_subbed = False
    return self.async_sub()

  def async_sub(self, retries=None):
    future = Future()

    def try_sub():
      self.verification_event.clear()
      for attempt in itertools.count():
        verb = 'subscribe' if self.should_be_subbed else 'unsubscribe'
        gerund = verb.replace('e', 'ing')
        noun = verb.replace('be', 'ption')

        logging.info(f'{gerund.capitalize()} WebSub server (attempt {attempt + 1})')

        timeout = parse_duration(config['websub_timeout'])
        if retries is None:
          retrying = ''
        else:
          retry_time = parse_duration(retries[min(attempt, len(retries) - 1)])
          retrying = f'. Retrying in {retry_time} seconds'

        try:
          # YouTube doesn't require us to do any discovering, so we can immediately proceed to (un)subscribing.
          response = requests.post(self.hub, data={
            'hub.callback': self.callback,
            'hub.mode': verb,
            'hub.topic': self.topic,
            'hub.lease_seconds': ceil(parse_duration(config['websub_lease_time'])),
            'hub.secret': self.secret,
          }, timeout=timeout)
        except requests.exceptions.Timeout:
          logging.error(f'WebSub {noun} request timed out after {timeout} seconds' + retrying)
        except:
          logging.exception(f'Got exception while {gerund} WebSub server' + retrying)
        else:
          if response.status_code != 202:
            logging.error(f'WebSub {noun} request failed with {response.status_code}: {response.text!r}' + retrying)
          elif not self.verification_event.wait(timeout):
            logging.error(f'Timed out after {timeout} seconds while waiting for WebSub {noun} verification request' + retrying)
          else:
            self.verification_event.clear()
            logging.info(f'Successfully {verb}d WebSub server')
            future.set_result(True)
            return

        if retries is None:
          break
        time.sleep(retry_time)

      logging.error(f'Failed to {verb} WebSub server')
      future.set_result(False)

    threading.Thread(target=try_sub, daemon=True).start()
    return future

  def handle_error(self, request, client_address):
    logging.exception('Got exception while processing a request in WebSub server')

class HttpRequestHandler(http.server.BaseHTTPRequestHandler):
  def do_GET(self):
    url = urlparse(self.path)
    if url.path != urlparse(self.server.callback).path:
      self.send_error(404)
      return

    query = dict(parse_qsl(url.query))
    try:
      if self.server.should_be_subbed and query['hub.mode'] == 'subscribe' and query['hub.topic'] == self.server.topic:
        lease = int(query['hub.lease_seconds'])
        logging.info(f'Received WebSub subscription verification request with a lease of {lease} seconds')

        self.send_response(202)
        self.end_headers()
        self.wfile.write(query['hub.challenge'].encode())

        def resubscribe():
          if self.server.should_be_subbed:
            logging.info('Resubscribing WebSub server')
            self.server.subscribe()
        timer = threading.Timer(max(lease - 5, 0), resubscribe) # 5 seconds should be enough to resubscribe just in time.
        timer.daemon = True
        timer.start()

        self.server.verification_event.set()

      elif not self.server.should_be_subbed and query['hub.mode'] == 'unsubscribe' and query['hub.topic'] == self.server.topic:
        logging.info(f'Received WebSub unsubscription verification request')

        self.send_response(202)
        self.end_headers()
        self.wfile.write(query['hub.challenge'].encode())

        self.server.verification_event.set()

      else:
        logging.info('Received an unwanted WebSub verification request')
        self.send_error(404)
    except (KeyError, ValueError):
      logging.info('Received an invalid WebSub verification request')
      self.send_error(400)

  def do_POST(self):
    if urlparse(self.path).path != urlparse(self.server.callback).path:
      self.send_error(404)
      return

    try:
      algorithm, _, signature = self.headers['X-Hub-Signature'].partition('=')
    except AttributeError:
      logging.info('Received an unsigned WebSub message')
      self.send_error(401)
      return
    else:
      logging.info('Received WebSub message')

    if algorithm not in {'sha1', 'sha256', 'sha384', 'sha512'}: # New algorithms may be added in the future.
      logging.warn(f'Unknown WebSub signature algorithm: {algorithm!r}')
      self.send_error(501)
      return

    try:
      content_length = self.headers['Content-Length'] # Doesn't http.server already check this by any chance?
    except AttributeError:
      logging.info('WebSub message has no Content-Length')
      self.send_error(411)
      return

    try:
      content_length = int(content_length)
    except ValueError:
      logging.info(f'WebSub message has malformed Content-Length: {content_length!r}')
      self.send_error(400)
      return

    if content_length > 100_000: # 100kB is a sane limit.
      logging.info(f'WebSub message too long: {content_length}')
      self.send_error(413)
      return

    content = self.rfile.read(content_length)

    self.send_response(202) # We "accept" invalid signatures to prevent brute-force attacks, as recommended by the W3C spec.

    if not hmac.compare_digest(signature, hmac.new(self.server.secret.encode(), content, algorithm).hexdigest()):
      logging.info('Failed to verify the authenticity of WebSub message')
      return

    if on_msg is None:
      logging.warn('No WebSub message handler has been provided')
    else:
      on_msg(content.decode())

  def log_message(self, format, *args): # The person who came up with this is insane.
    logging.info(f'WebSub server says {format % args!r}')

console.begin('websub')
console.register('start',       None, 'starts the WebSub server',       start)
console.register('stop',        None, 'stops the WebSub server',        stop)
console.register('subscribe',   None, 'subscribes the WebSub server',   lambda: server.subscribe())
console.register('unsubscribe', None, 'unsubscribes the WebSub server', lambda: server.unsubscribe())
console.end()
