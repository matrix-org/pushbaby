#!/usr/bin/env python

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

import os
import codecs
from setuptools import setup


here = os.path.abspath(os.path.dirname(__file__))


def read_file(names, encoding="utf-8"):
    file_path = os.path.join(here, *names)
    if encoding:
        with codecs.open(file_path, encoding=encoding) as f:
            return f.read()
    else:
        with open(file_path, "rb") as f:
            return f.read()


def exec_file(names):
    code = read_file(names, encoding=None)
    result = {}
    exec(code, result)
    return result

setup(
    name="pushbaby",
    version=exec_file(("pushbaby", "version.py",))["__version__"],
    packages=['pushbaby'],
    license="Apache License, Version 2.0",
    description="APNS library using gevent",
    url="https://github.com/matrix-org/pushbaby",
    author="matrix.org",
    author_email="dave@matrix.org",
    long_description=read_file(("README.rst",)),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 2",
    ],
    keywords="apns push",
    install_requires=[
        "gevent>=1.0.1",
    ],
)
