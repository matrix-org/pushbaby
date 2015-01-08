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

import copy

from .aps import json_for_aps


class BodyTooLongException(Exception):
    pass


def is_too_long(aps, max_length=2048):
    """
    Returns True if the given APS dictionary is too long for a push.
    Note that the maximum is now 2kB "In iOS 8 and later" although in
    practice, payloads over 256 bytes (the old limit) are still
    delivered to iOS 7 or earlier devices.
    """
    return len(json_for_aps(aps)) > max_length


def truncate(aps, max_length=2048):
    aps = copy.copy(aps)

    # first ensure all our choppables are unicode objects.
    # We need them to be for truncating to work and this
    # makes more sense than checking every time.
    for c in _choppables_for_aps(aps):
        val = _choppable_get(aps, c)
        if isinstance(val, str):
            _choppable_put(aps, c, val.decode('utf8'))

    # chop off whole unicode characters until it fits (or we run out of chars)
    while is_too_long(aps, max_length):
        longest = _longest_choppable(aps)
        if longest is None:
            raise BodyTooLongException()

        txt = _choppable_get(aps, longest)
        # Note that python's support for this is actually broken on some OSes
        # (see test_truncate.py)
        txt = txt[:-1]
        _choppable_put(aps, longest, txt)

    return aps


def _choppables_for_aps(aps):
    ret = []
    if 'alert' not in aps:
        return ret

    alert = aps['alert']
    if isinstance(alert, str) or isinstance(alert, unicode):
        ret.append(('alert',))
    elif isinstance(alert, dict):
        if 'body' in alert:
            ret.append(('alert.body',))
        if 'loc-args' in alert:
            ret.extend([('alert.loc-args', i) for i in range(len(alert['loc-args']))])

    return ret


def _choppable_get(aps, choppable):
    if choppable[0] == 'alert':
        return aps['alert']
    elif choppable[0] == 'alert.body':
        return aps['alert']['body']
    elif choppable[0] == 'alert.loc-args':
        return aps['alert']['loc-args'][choppable[1]]


def _choppable_put(aps, choppable, val):
    if choppable[0] == 'alert':
        aps['alert'] = val
    elif choppable[0] == 'alert.body':
        aps['alert']['body'] = val
    elif choppable[0] == 'alert.loc-args':
        aps['alert']['loc-args'][choppable[1]] = val


def _longest_choppable(aps):
    longest = None
    length_of_longest = 0
    for c in _choppables_for_aps(aps):
        val = _choppable_get(aps, c)
        val_len = len(val.encode('utf8'))
        if val_len > length_of_longest:
            longest = c
            length_of_longest = val_len
    return longest
