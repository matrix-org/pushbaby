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

import logging
import random

from pushbaby.pushconnection import PushConnection, ConnectionDeadException
from pushbaby.feedbackconnection import FeedbackConnection


logger = logging.getLogger(__name__)


class PushBaby:
    """
    This class is all that you should need to use in the majority of cases.
    Sending a push can be achieved using the send() method.
    To receive errors, set the 'on_push_failed' member like so:

        def on_push_failed(token, identifier, status):
            [handle error]

        pb = PushBaby(cerfile='mycert.pem')
        pb.on_push_failed = on_push_failed
    """
    ADDRESSES = {
        'prod': ('gateway.push.apple.com', 2195),
        'sandbox': ('gateway.sandbox.push.apple.com', 2195)
    }
    FEEDBACK_ADDRESSES = {
        'prod': ('feedback.push.apple.com', 2196),
        'sandbox': ('feedback.sandbox.push.apple.com', 2196)
    }

    def __init__(self, certfile, keyfile=None, platform='sandbox', feedback_address=None):
        """
        Args:
            certfile: Path to a certificate file in PEM format
                      This may also include the private key.
            keyfile: Path to the private key file in PEM format
            platform: The platform to use ('sandbox' or 'prod')
                      or a tuple of hostname and port.
        """
        self.fbaddress = None
        if isinstance(platform, str):
            if platform in PushBaby.ADDRESSES:
                self.address = PushBaby.ADDRESSES[platform]
                self.fbaddress = PushBaby.FEEDBACK_ADDRESSES[platform]
            else:
                self.address = (platform, 2195)
        else:
            self.address = platform

        if feedback_address:
            self.fbaddress = feedback_address

        if not self.fbaddress:
            logger.warn(
                "gateway address manually configured but no feedback_address " +
                "supplied. Fetching feedback will not work"
            )

        self.sock = None
        self.certfile = certfile
        self.keyfile = keyfile
        self.conns = []
        self.on_push_failed = None
        self.on_feedback = None

    def send(self, payload, token, expiration=None, priority=None, identifier=None):
        """
        Attempts to send a push message. On network failures, progagates the exception.
        It is advised to make all text in the payload dictionary unicode objects and not
        mix unicode objects and str objects. If str objects are used, they must be
        in UTF-8 encoding.
        Args:
            payload (dict): The dictionary payload of the push to send
            token (str): token to send the push to (raw, unencoded bytes)
            expiration (int, seconds): When the message becomes irrelevant (time in seconds, as from time.time())
            priority (int): Integer priority for the message as per Apple's documentation
            identifier (any): optional identifier that will be returned if the push fails.
                        This is opaque to the library and not limited to 4 bytes.
        Throws:
            BodyTooLongException: If the payload body is too long and cannot be truncated to fit
        """

        # we only use one conn at a time currently but we may as well do this...
        while True:
            if len(self.conns) == 0:
                self.conns.append(PushConnection(self, self.address, self.certfile, self.keyfile))
            conn = random.choice(self.conns)
            try:
                conn.send(payload, token, expiration=expiration, priority=priority, identifier=identifier)
                break
            except:
                logger.info("Connection died: removing")
                self.conns.remove(conn)

    def messages_in_flight(self):
        """
        Returns True if there are messages waiting to be sent or that we're
        still waiting to see if errors occur for.
        This can be used to determine whether it is safe to shut down the
        application.
        """
        for c in self.conns:
            if c.messages_in_flight():
                return True
        return False


    def get_all_feedback(self):
        """
        Connects to the feedback service and returns any feedback that is sent
        as a list of FeedbackItem objects.

        Blocks the current greenlet until all feedback is returned.

        If a network error occurs before any feedback is received, it is
        propagated to the caller. Otherwise, it is ignored and the feedback
        that had arrived is returned.
        """
        if not self.fbaddress:
            raise Exception("Attempted to fetch feedback but no feedback_address supplied")

        fbconn = FeedbackConnection(self, self.fbaddress, self.certfile, self.keyfile)
        return fbconn.get_all()
