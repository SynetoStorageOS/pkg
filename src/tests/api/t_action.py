#!/usr/bin/python
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import unittest

import pkg.actions as action

class TestActions(unittest.TestCase):

        def test_action_parser(self):
                action.fromstr("file 12345 name=foo")
                action.fromstr("file 12345 name=foo attr=bar")
                action.fromstr("file 12345 name=foo attr=bar attr=bar")

                action.fromstr("file 12345 name=foo     attr=bar")
                action.fromstr("file 12345 name=foo     attr=bar   ")
                action.fromstr("file 12345 name=foo     attr=bar   ")

                action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\"")
                action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\"")

                action.fromstr("driver alias=pci1234,56 alias=pci4567,89 class=scsi name=lsimega")

        def test_action_tostr(self):
                str(action.fromstr("file 12345 name=foo"))
                str(action.fromstr("file 12345 name=foo attr=bar"))
                str(action.fromstr("file 12345 name=foo attr=bar attr=bar"))

                str(action.fromstr("file 12345 name=foo     attr=bar"))
                str(action.fromstr("file 12345 name=foo     attr=bar   "))
                str(action.fromstr("file 12345 name=foo     attr=bar   "))

                str(action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\""))
                str(action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\""))

                str(action.fromstr("driver alias=pci1234,56 alias=pci4567,89 class=scsi name=lsimega"))

        def test_action_errors(self):
                # bogus action
                self.assertRaises(KeyError, action.fromstr, "moop")

                # bad quoting
                self.assertRaises(ValueError, action.fromstr,
                     "file 12345 name=\"foo bar")

                self.assertRaises(ValueError, action.fromstr,
                     "file 12345 \"name=foo bar")

                #self.assertRaises(ValueError, action.fromstr,
                #    "file 12345 na\"me=foo bar")

                #self.assertRaises(ValueError, action.fromstr,
                #    "file 12345 name=foo\"bar")

                self.assertRaises(ValueError, action.fromstr, "file 1234 =\"\"")

                # bogus attributes
                self.assertRaises(ValueError, action.fromstr, "file =")
                self.assertRaises(ValueError, action.fromstr, "file 1234 broken")
                self.assertRaises(ValueError, action.fromstr, "file 1234 broken=")
                self.assertRaises(ValueError, action.fromstr, "file 1234 =")
                self.assertRaises(ValueError, action.fromstr, "file 1234 ==")
                self.assertRaises(ValueError, action.fromstr, "file 1234 ===")
                pass


if __name__ == "__main__":
        unittest.main()
