# -*- coding: utf-8 -*-
# pylint: disable=
""" Filter condition tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""
import logging
import time
import unittest

import parsimonious
import pytest

from pyrosimple.util import matching
from pyrosimple.util.parts import Bunch


log = logging.getLogger(__name__)
log.debug("module loaded")


@pytest.mark.parametrize(
    "cond",
    [
        "//",
        "/test/",
        "/.*/",
        "name=*test*",
        "name=//",
        "name!=//",
        "name=/test/",
        "name=/.*/",
        "name=/.+/",
        "Roger.Rabbit?",
        "name=Roger.Rabbit?",
        "Bang!Bang!Bang!",
        "name=Bang!Bang!Bang!",
        "Æon",
        "name=*Æon*",
        "name==test",
        "number=0",
        "number>0",
        "number>=0",
        "number=+0",
        "number<0",
        "number<=0",
        "number=-0",
        "name=/[0-9]/",
        "number!=0",
        "number<>0",
        "name==/.*/",
        "name=*test*",
        "name=test-test2.mkv",
        'name="The Thing"',
        'name="*The Thing*"',
        "name=test name=test2",
        "name=test OR name=test2",
        "[ name=test OR name=test2 ]",
        "NOT [ name=test OR name=test2 ]",
        "NOT [ name=test name=test2 ]",
        "NOT [ name=test test2 ]",
        "NOT [ name=test OR alias=// ]",
        "test=five [ name=test OR name=test2 ]",
        "test=five NOT [ name=test OR name=test2 ]",
        "test=five OR NOT [ name=test name=test2 ]",
        "test=five OR NOT [ name=test OR name=test2 ]",
        "name=arch-* OR [ alias=Ubuntu loaded>1w ]",
    ],
)
def test_parsim_good_conditions(cond):
    matching.QueryGrammar.parse(cond)


@pytest.mark.parametrize(
    "cond",
    [
        "",
        "NOT",
        "NOT OR",
        "[ name!=name",
        "name==name ]",
    ],
)
def test_parsim_error_conditions(cond):
    with pytest.raises(parsimonious.exceptions.ParseError):
        matching.QueryGrammar.parse(cond)


@pytest.mark.parametrize(
    ("cond", "expected"),
    [
        ("name=arch", '"string.contains_i=$d.name=,\\"arch\\""'),
    ],
)
def test_conditions_prefilter(cond, expected):
    filt = (
        matching.MatcherBuilder().visit(matching.QueryGrammar.parse(cond)).pre_filter()
    )
    assert str(filt) == expected


@pytest.mark.parametrize(
    ("matcher", "item"),
    [
        ("name=arch", Bunch(name="arch")),
        ("name=/arch/i", Bunch(name="ARCH")),
        ("name=/ar.*/i", Bunch(name="ARCH")),
        ("name=ARCH", Bunch(name="ARCH")),
        ("name=rtörrent", Bunch(name="rtörrent")),
        ("name={{d.alias}}", Bunch(name="ubuntu",alias="ubuntu")),
        ("name={{d.alias}}*", Bunch(name="ubuntu-server",alias="ubuntu")),
        ("name=rtör*", Bunch(name="rtörrent")),
        ("name=arch*", Bunch(name="arch-linux")),
        ("name=*arch", Bunch(name="base-arch")),
        ("name=/arch/", Bunch(name="base-arch")),
        ("name=/arch$/", Bunch(name="base-arch")),
        ('message=""', Bunch(message="")),
        ('message!=""', Bunch(message="Oh no!")),
        ("is_complete=no", Bunch(is_complete=False)),
        ("ratio>2", Bunch(ratio=5.0)),
        ("ratio>2 ratio<6.0", Bunch(ratio=5.0)),
        ("size>1G", Bunch(size=2 * (1024**3))),
        ("size>1G", Bunch(size=2 * (1024**3))),
        ("leechtime>1h", Bunch(leechtime=60 * 60 * 2)),
        ("completed>2h", Bunch(completed=time.time() - (60 * 60 * 2))),
        ("completed<1h", Bunch(completed=time.time() - 1)),
        ("tagged=test", Bunch(tagged=["test", "notest"])),
        ("tagged=notest", Bunch(tagged=["test", "notest"])),
        (
            "files=test*",
            Bunch(files=[Bunch(path="test/test.mkv"), Bunch(path="test.nfo")]),
        ),
    ],
)
def test_matcher(matcher, item):
    m = matching.create_matcher(matcher)
    assert m.match(item)


@pytest.mark.parametrize(
    ("matcher", "item"),
    [
        ("name=arch", Bunch(name="ARCH")),
        ("name=ARCH", Bunch(name="arch")),
        ("name=arch", Bunch(name="asdfsafad")),
        ("name!=arch*", Bunch(name="arch-linux")),
        ("name!=/arch$/", Bunch(name="base-arch")),
        ("is_complete=yes", Bunch(is_complete=False)),
        ("ratio<2", Bunch(ratio=5.0)),
        ("size<1G", Bunch(size=2 * (1024**3))),
        ("leechtime<1h", Bunch(leechtime=60 * 60 * 2)),
        ("completed>1h", Bunch(completed=time.time() - 1)),
        ("tagged=:test", Bunch(tagged=["test", "notest"])),
        ("tagged=faketest", Bunch(tagged=["test", "notest"])),
    ],
)
def test_matcher_fail(matcher, item):
    m = matching.create_matcher(matcher)
    assert not m.match(item)
