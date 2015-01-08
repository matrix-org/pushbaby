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

from pushbaby.aps import json_for_aps


class ApsTestCase(unittest.TestCase):
    def test_efficient_multibyte(self):
        txt = u"\U0001F414"
        aps = {
            'alert': txt
        }
        json_with_multibyte = json_for_aps(aps)
        # Shortest encoding uses literal UTF8, not \u escape sequences, and
        # doesn't put unneccesary space after commas and colons.
        shortest_encoding = u"{\"aps\":{\"alert\":\"\U0001F414\"}}".encode('utf8')

        self.assertEquals(shortest_encoding, json_with_multibyte)
