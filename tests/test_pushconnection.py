# -*- coding: utf-8 -*-
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

import unittest

from pushbaby import PushBaby

import gevent.socket
import gevent.event

import struct
import logging
import json
import time

logging.basicConfig(level=logging.DEBUG)


class DummyPushServer:
    """
    dummy (non-ssl) push server
    """

    def __init__(self, ut):
        self.ut = ut
        self.cs = None
        self.csevent = gevent.event.Event()
        self.listen_greenlet = None
        self.reject_code = None

    def start(self):
        self.sock = gevent.socket.socket(gevent.socket.AF_INET, gevent.socket.SOCK_STREAM)
        self.sock.bind(('localhost', 0))
        self.sock.listen(1)
        self.listen_greenlet = gevent.spawn(self.listen_loop)

    def stop(self):
        self.listen_greenlet.kill()
        self.sock.close()
        if self.cs:
            self.cs.close()

    def listen_loop(self):
        while True:
            (clisock, addr) = self.sock.accept()
            self.cs = clisock
            self.csevent.set()

    def get_push(self):
        self.csevent.wait(timeout=0.1)
        command = struct.unpack("!B", self.cs.recv(1))[0]
        if command != 2:
            self.ut.fail("Got unknown command: %d" % (command,))
        rawlen = self.cs.recv(4)
        framelen = struct.unpack("!I", rawlen)[0]
        frame = self.cs.recv(framelen)
        offset = 0
        push = {}
        rawid = None
        while offset < framelen:
            itemid = struct.unpack("!B", frame[offset])[0]
            offset += 1
            itemdatalen = struct.unpack("!H", frame[offset:offset+2])[0]
            offset += 2
            itemdata = frame[offset:offset+itemdatalen]
            offset += itemdatalen
            if itemid == 1:
                push['token'] = itemdata
            elif itemid == 2:
                push['payload'] = itemdata
            elif itemid == 3:
                rawid = itemdata
            elif itemid == 4:
                push['expiration'] = struct.unpack("!I", itemdata)[0]
            elif itemid == 5:
                push['priority'] = struct.unpack("!B", itemdata)[0]

        if self.reject_code is not None:
            self.cs.send(struct.pack("!BB", 8, self.reject_code)+rawid)
            self.cs.close()
            self.cs = None
            self.csevent.clear()

        return push

    def get_addr(self):
        return self.sock.getsockname()

    def set_reject_code(self, rc):
        self.reject_code = rc
        

class ConnectionTestCase(unittest.TestCase):
    def on_push_failed(self, token, identifier, status):
        self.failure = (status, token, identifier, status)
        self.failure_event.set()

    def setUp(self):
        self.failure_event = gevent.event.Event()
        self.failure = None 
        self.srv = DummyPushServer(self)
        self.srv.start()

    def tearDown(self):
        self.srv.stop()

    def test_retry(self):
        pb = PushBaby(certfile=None, platform=self.srv.get_addr())
        pb.on_push_failed = self.on_push_failed
        pb.send({'alert': u'1'}, '1')
        self.srv.get_push()
        self.assertEquals(None, self.failure)
        self.srv.set_reject_code(10)
        pb.send({'alert': u'2'}, '2')
        pb.send({'alert': u'3'}, '3')
        self.assertIsNotNone(self.srv.get_push())
        self.srv.set_reject_code(None)
        # we should not be notified about this failure,
        # it should just get resent
        self.assertEquals(None, self.failure)
        p = self.srv.get_push()
        aps = json.loads(p['payload'])['aps']
        self.assertEquals(u'2', aps['alert'])
        self.assertEquals(u'2', p['token'])
        # as should the one we sent subsequently
        p = self.srv.get_push()
        aps = json.loads(p['payload'])['aps']
        self.assertEquals(u'3', aps['alert'])
        self.assertEquals(u'3', p['token'])

    def test_failure(self):
        pb = PushBaby(certfile=None, platform=self.srv.get_addr())
        pb.on_push_failed = self.on_push_failed
        myid = 'some identifier'
        self.srv.set_reject_code(8)
        pb.send({'alert': u'1'}, '1', identifier=myid)
        self.srv.get_push()
        self.failure_event.wait(timeout=0.1)
        self.assertIsNotNone(self.failure)
        self.assertIs(myid, self.failure[2])
 
    def test_params(self):
        pb = PushBaby(certfile=None, platform=self.srv.get_addr())
        pb.on_push_failed = self.on_push_failed
        exp = time.time() + 3600
        pb.send({'alert': u'1'}, '1', priority=5, expiration=exp)
        p = self.srv.get_push()
        self.assertEquals(5, p['priority'])
        self.assertEquals(long(exp), p['expiration'])
