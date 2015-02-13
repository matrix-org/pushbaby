# Copyright 2015 OpenMarket Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import gevent.ssl
import gevent.socket
import gevent.timeout
import gevent.event
import gevent.queue

import logging
import struct
import time
import sys
import errno

from pushbaby.truncate import truncate
from pushbaby.aps import json_for_payload
import pushbaby.errors


logger = logging.getLogger(__name__)


class PushConnection:
    COMMAND_SENDPUSH = 2
    COMMAND_ERROR = 8

    ITEM_DEVICE_TOKEN = 1
    ITEM_PAYLOAD = 2
    ITEM_IDENTIFIER = 3
    ITEM_EXPIRATION = 4
    ITEM_PRIORITY = 5

    MAX_ERROR_WAIT_SEC = 60
    MAX_PUSHES_PER_CONNECTION = 2**31
    MAX_CONN_IDLE_SEC = 30
    CONN_TIMEOUT = 10

    class SentMessage:
        def __init__(self, sendts, token, payload, expiration, priority, identifier):
            self.sendts = sendts
            self.token = token

            self.payload = payload
            self.expiration = expiration
            self.priority = priority
            self.identifier = identifier

    def __init__(self, pushbaby, address, certfile, keyfile):
        self.pushbaby = pushbaby
        self.address = address
        self.certfile = certfile
        self.keyfile = keyfile
        self.seq = -1
        self.sock = None
        self.alive = True
        self.useable = True
        self.send_queue = gevent.queue.Queue()
        self.sent = {}
        self.last_push_sent = None
        self.last_failed_seq = None
        self.open_event = None

    def _open_connection(self):
        logger.info("Establishing new connection to %s", self.address)
        self.sock = gevent.socket.create_connection(self.address)
        self.sock.settimeout(10.0)
        # attempt to set the TCP_USER_TIMEOUT sockopt (will only work on Linux)
        # (from /usr/include/linux/tcp.h: #define TCP_USER_TIMEOUT 18)
        # Without this, connections will take 15 minutes or much, much longer to
        # time out if the connection drops which is nonideal since we'll be sending
        # push into the void during that time
        try:
            self.sock.setsockopt(gevent.socket.IPPROTO_TCP, 18, PushConnection.CONN_TIMEOUT * 1000)
        except gevent.socket.error:
            logger.warn(
                "Couldn't set socket timeout (only works on Linux >= 2.6.37). " +
                "Unresponsive connections will take a long time to timeout and " +
                "pushes during that time will be lost."
            )
        # We use a non-ssled connection if both certfile and keyfile
        # are None. This is useful only for testing. None is not the
        # default for certfile so the app would have to explicitly
        # specify None.
        if self.certfile or self.keyfile:
            self.sock = gevent.ssl.wrap_socket(
                self.sock, keyfile=self.keyfile, certfile=self.certfile
            )
        gevent.spawn(self._read_loop)
        gevent.spawn(self._write_loop)

    def _close_connection(self):
        self.alive = False
        self.useable = False
        try:
            self.sock.close()
        except:
            logger.exception("Caught exception closing socket")

    def _retire_connection(self):
        self.useable = False
        self.retired_at = time.time()

    def _read_loop(self):
        # This is a little lazy since there is only one command, so
        # we know we'll always have to read exactly 5 bytes after the command
        while self.alive:
            buf = ''
            while len(buf) < 6 and self.alive:
                self.prune_sent()

                try:
                    thisbuf = self.sock.recv(6 - len(buf))
                    if thisbuf == '':
                        logger.info("Connection closed remotely")
                        self._close_connection()
                        continue
                    buf += thisbuf
                except gevent.ssl.SSLError as e:
                    if e == gevent.ssl._SSLErrorReadTimeout:
                        pass
                    else:
                        # Note that we do not attempt to do any resending if the
                        # connection drops, even through we could have lost pushes.
                        # The problem is that we don't really have any way of knowing
                        # what to resend so we could end up generating lots of dupes.
                        # One way may be to use TIOCOUTQ to see how much data the
                        # other side hasn't ACKed.
                        logger.exception("Caught exception reading from socket: closing")
                        self._close_connection()
                        continue
                except gevent.socket.error as e:
                    if e.errno == errno.ECONNRESET:
                        logger.info("Connection closed remotely")
                    else:
                        logger.exception("Caught exception reading from socket: closing")
                    self._close_connection()
                    continue
                except:
                    logger.exception("Caught exception reading from socket: closing")
                    self._close_connection()
                    continue

                if self.last_push_sent:
                    secs_since_last_used = time.time() - self.last_push_sent
                    if self.useable and secs_since_last_used > PushConnection.MAX_CONN_IDLE_SEC:
                        logger.info("Connection unused for %f seconds: retiring", secs_since_last_used)
                        self._retire_connection()
                    if not self.useable and secs_since_last_used > PushConnection.MAX_ERROR_WAIT_SEC:
                        # we've waited for as long as we want to for errors, and we're not going to
                        # send anything else, so our work here is done.
                        logger.info("Connection retired and last used %f seconds ago: closing", secs_since_last_used)
                        self._close_connection()

            if self.alive:
                (command, status, seq) = struct.unpack("!BBI", buf)
                if command != PushConnection.COMMAND_ERROR:
                    # if we get a command we don't recognise, we must close the connection.
                    # There's no framing so we can't just skip past anything unknown
                    # because we'd have no idea how much to skip.
                    logger.error("Recieved unknown command %d: closing connection", command)
                    self._close_connection()

                self._push_failed(status, seq)
                # we now expect the connection to be closed from the other end

    def _write_loop(self):
        # we keep running while there are things in the queue because
        # we can't quite and leave things in the queue or they'll end
        # up blocked forever
        while self.alive or not self.send_queue.empty():
            try:
                job = self.send_queue.get(block=True, timeout=10.0)
                job()
            except gevent.queue.Empty:
                continue

    def _push_failed(self, status, seq):
        self.last_failed_seq = seq
        self.prune_sent()

        # A push connection is no longer useable once we've had an error down
        # so retire it
        self._retire_connection()

        if seq in self.sent:
            failed = self.sent[seq]
            if status == pushbaby.errors.SHUTDOWN:
                # we'll retry this one automatically
                logger.info("Push failed with SHUTDOWN status: retying")
                self.pushbaby.send(failed.payload, failed.token, failed.priority, failed.expiration, failed.identifier)
            else:
                logger.warn("Push to token %s failed with status %d", failed.token, status)
                if self.pushbaby.on_push_failed:
                    self.pushbaby.on_push_failed(failed.token, failed.identifier, status)

            # Any pushes after a failed one are not processed and need to be resent
            # we've already pruned out the ones before so if we remove the failed one,
            # we resend all the remaining ones
            del self.sent[seq]
            logger.info("Retrying %d pushes sent after failed push", len(self.sent))
            for sm in self.sent.values():
                self.pushbaby.send(sm.payload, sm.token, sm.priority, sm.expiration, sm.identifier)
        else:
            logger.error("Got a failure for seq %d that we don't remember!", seq)

    def messages_in_flight(self):
        """
        Returns True if there are messages waiting to be sent or that we're
        still waiting to see if errors occur for.
        """
        self.prune_sent()
        if not self.send_queue.empty() or len(self.sent) > 0:
            return True
        return False

    def send(self, payload, token, expiration=None, priority=None, identifier=None):
        if not self.alive:
            raise ConnectionDeadException()
        if not self.useable:
            raise ConnectionDeadException()
        if not self.sock:
            # We'll yield back to the hub whilst the connection is
            # opened so if another send attempt starts in that time,
            # wait for the other greenlet to finish: don't try to open
            # it again!
            if self.open_event is None:
                self.open_event = gevent.event.Event()
                try:
                    self._open_connection()
                finally:
                    self.open_event.set()
            else:
                self.open_event.wait()
                if not self.sock:
                    raise ConnectionDeadException()

        sent_event = gevent.event.Event()
        res = {}

        def sendpush():
            try:
                res['ret'] = self._reallysend(payload, token, expiration, priority, identifier)
            except:
                logger.exception("Caught exception sending push")
                res['ex'] = sys.exc_info()[1]
            sent_event.set()
        self.send_queue.put(sendpush)
        sent_event.wait()
        if 'ex' in res:
            raise ConnectionDeadException()
        else:
            return res['ret']

    def _reallysend(self, payload, token, expiration=None, priority=None, identifier=None):
        """
        Args:
            payload (dict): The payload dictionary of the push to send
            descriptor (any): Opaque variable that is passed back to the pushbaby on failure
        """

        if not self.alive:
            raise ConnectionDeadException()
        if not self.useable:
            raise ConnectionDeadException()
        seq = self._nextSeq()
        if seq >= PushConnection.MAX_PUSHES_PER_CONNECTION:
            # IDs are 4 byte so rather than worry about wrapping IDs, just make a new connection
            # Note we don't close the connection because we want to wait to see if any errors arrive
            self._retire_connection()

        payload_str = json_for_payload(truncate(payload))
        items = ''
        items += self._apns_item(PushConnection.ITEM_DEVICE_TOKEN, token)
        items += self._apns_item(PushConnection.ITEM_PAYLOAD, payload_str)
        items += self._apns_item(PushConnection.ITEM_IDENTIFIER, seq)
        if expiration:
            items += self._apns_item(PushConnection.ITEM_EXPIRATION, expiration)
        if priority:
            items += self._apns_item(PushConnection.ITEM_PRIORITY, priority)

        apnsFrame = struct.pack("!BI", PushConnection.COMMAND_SENDPUSH, len(items)) + items

        try:
            written = 0
            while written < len(apnsFrame):
                written += self.sock.send(apnsFrame[written:])
        except:
            logger.exception("Caught exception sending push")
            raise
        self.sent[seq] = PushConnection.SentMessage(
            time.time(), token, payload, expiration, priority, identifier
        )
        self.last_push_sent = time.time()

    def _apns_item(self, item_id, data):
        if item_id == PushConnection.ITEM_IDENTIFIER:
            # identifier (4 bytes)
            # strictly speaking this is just bytes do we could just
            # send it in host byte order but we may as well keep
            # everything in network byte order
            data = struct.pack("!I", data)
        elif item_id == PushConnection.ITEM_EXPIRATION:
            # expiration date (4 bytes)
            data = struct.pack("!I", long(data))
        elif item_id == PushConnection.ITEM_PRIORITY:
            # priority (1 byte)
            data = struct.pack("!B", data)
        # anything else is raw data and we don't need to pack

        return struct.pack("!BH", item_id, len(data)) + data

    def _nextSeq(self):
        self.seq += 1
        return self.seq

    def prune_sent(self):
        for seq, m in self.sent.items():
            # We say it's safe to assume that anything we sent more than this
            # long ago would have failed by now if it was going to fail
            if m.sendts < time.time() - PushConnection.MAX_ERROR_WAIT_SEC:
                del self.sent[seq]
            # If we know a push has failed, we can deduce that all previous
            # pushes succeeded
            if self.last_failed_seq and seq < self.last_failed_seq:
                del self.sent[seq]


class ConnectionDeadException(Exception):
    pass
