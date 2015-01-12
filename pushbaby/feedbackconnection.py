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
import errno

from .feedback import FeedbackItem


logger = logging.getLogger(__name__)


class FeedbackConnection:
    def __init__(self, pushbaby, address, certfile, keyfile):
        self.pushbaby = pushbaby
        self.address = address
        self.certfile = certfile
        self.keyfile = keyfile
        self.sock = None

    def get_all(self):
        if not self.sock:
            self._open_connection()

        feedback = []
        connection_alive = True
        try:
            while connection_alive:
                buf = ''
                while len(buf) < 6:
                    gotdata = self.sock.recv(6-len(buf))
                    if gotdata == '':
                        connection_alive = False
                        break
                    buf += gotdata
                if not connection_alive:
                    break
                (ts, toklen) = struct.unpack("!IH", buf)
                buf = ''
                while len(buf) < toklen:
                    gotdata = self.sock.recv(toklen-len(buf))
                    if gotdata == '':
                        connection_alive = False
                        break
                    buf += gotdata
                if not connection_alive:
                    break
                feedback.append(FeedbackItem(buf, float(ts)))
        except gevent.socket.error as e:
            if not e.errno == errno.ECONNRESET:
                logger.exception("Caught exception whilst getting feedback")
                # If we've already got feedback, return it: we won't get it again
                if len(feedback) == 0:
                    raise
        except gevent.ssl.SSLError as e:
            logger.exception("Caught exception whilst getting feedback")
            # If we've already got feedback, return it: we won't get it again
            if len(feedback) == 0:
                raise
        # NB. we do not catch timeout errors here, ie. we consider them
        #     to be fatal. If it's taking that long to get a response,
        #     something is very wrong with our connection to the
        #     feedback server so we should probaly just come back
        #     tomorrow.
        try:
            self.sock.close()
        except:
            logger.exception("Error closing socket")

        logger.info("Returning %d feedback items", len(feedback))
        return feedback

    def _open_connection(self):
        logger.info("Establishing new feedback connection to %s", self.address)
        self.sock = gevent.socket.create_connection(self.address)
        self.sock.settimeout(10.0)
        # We use a non-ssled connection if both certfile and keyfile
        # are None. This is useful only for testing. None is not the
        # default for certfile so the app would have to explicitly
        # specify None.
        if self.certfile or self.keyfile:
            self.sock = gevent.ssl.wrap_socket(
                self.sock, keyfile=self.keyfile, certfile=self.certfile
            )
