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

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import re
import time
import unittest
import shutil
from stat import *

class TestPkgVariants(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        bronze10 = """
        open bronze@1.0,5.11-0
        add set name=variant.arch value=sparc value=i386 value=zos
        add dir mode=0755 owner=root group=bin path=/etc
        add file /tmp/bronze_sparc/etc/motd mode=0555 owner=root group=bin path=etc/motd variant.arch=sparc
        add file /tmp/bronze_i386/etc/motd mode=0555 owner=root group=bin path=etc/motd variant.arch=i386
        add file /tmp/bronze_zos/etc/motd mode=0555 owner=root group=bin path=etc/motd variant.arch=zos
        add file /tmp/bronze_zone/etc/nonglobal_motd mode=0555 owner=root group=bin path=etc/zone_motd variant.opensolaris.zone=nonglobal
        add file /tmp/bronze_zone/etc/global_motd mode=0555 owner=root group=bin path=etc/zone_motd variant.opensolaris.zone=global
        add file /tmp/bronze_zone/etc/sparc_nonglobal mode=0555 owner=root group=bin path=etc/zone_arch variant.arch=sparc variant.opensolaris.zone=nonglobal
        add file /tmp/bronze_zone/etc/i386_nonglobal mode=0555 owner=root group=bin path=etc/zone_arch variant.arch=i386 variant.opensolaris.zone=nonglobal
        add file /tmp/bronze_zone/etc/zos_nonglobal mode=0555 owner=root group=bin path=etc/zone_arch variant.arch=zos variant.opensolaris.zone=nonglobal
        add file /tmp/bronze_zone/etc/sparc_global mode=0555 owner=root group=bin path=etc/zone_arch variant.arch=sparc variant.opensolaris.zone=global
        add file /tmp/bronze_zone/etc/i386_global mode=0555 owner=root group=bin path=etc/zone_arch variant.arch=i386 variant.opensolaris.zone=global
        add file /tmp/bronze_zone/etc/zos_global mode=0555 owner=root group=bin path=etc/zone_arch variant.arch=zos variant.opensolaris.zone=global
        add file /tmp/bronze_zone/false mode=0555 owner=root group=bin path=etc/isdebug variant.debug.kernel=false 
        add file /tmp/bronze_zone/true mode=0555 owner=root group=bin path=etc/isdebug variant.debug.kernel=true
        close"""

        silver10 = """
        open silver@1.0,5.11-0
        add set name=variant.arch value=i386
        add dir mode=0755 owner=root group=bin path=/etc
        add file /tmp/bronze_i386/etc/motd mode=0555 owner=root group=bin path=etc/motd variant.arch=i386
        close"""

        misc_files = [ 
                "/tmp/bronze_sparc/etc/motd",
                "/tmp/bronze_i386/etc/motd",
                "/tmp/bronze_zos/etc/motd",
                "/tmp/bronze_zone/etc/nonglobal_motd",
                "/tmp/bronze_zone/etc/global_motd",
                "/tmp/bronze_zone/etc/i386_nonglobal",
                "/tmp/bronze_zone/etc/sparc_nonglobal",
                "/tmp/bronze_zone/etc/zos_nonglobal",
                "/tmp/bronze_zone/etc/i386_global",
                "/tmp/bronze_zone/etc/sparc_global",
                "/tmp/bronze_zone/etc/zos_global",
                "/tmp/bronze_zone/false",
                "/tmp/bronze_zone/true",
                ]

        def setUp(self):
                print "setUP"
                testutils.SingleDepotTestCase.setUp(self)
                for p in self.misc_files:
                        path = os.path.dirname(p)
                        if not os.path.exists(path):
                                os.makedirs(path)
                        f = open(p, "w")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(p)
                        f.close()
                        self.debug("wrote %s" % p)
                
        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)

        def test_variant_1(self):
                self.__test_common("no-change", "no-change")
        def test_old_zones_pkgs(self):
                self.__test_common("variant.opensolaris.zone", "opensolaris.zone")

        def __test_common(self, orig, new):
                depot = self.dc.get_depot_url()
                self.pkgsend_bulk(depot, self.bronze10.replace(orig, new))
                self.pkgsend_bulk(depot, self.silver10.replace(orig, new))

                self.__vtest(depot, "sparc", "global")
                self.__vtest(depot, "i386", "global")
                self.__vtest(depot, "zos", "global", "true")
                self.__vtest(depot, "sparc", "nonglobal", "true")
                self.__vtest(depot, "i386", "nonglobal", "false")
                self.__vtest(depot, "zos", "nonglobal", "false")

                self.image_create(depot, 
                    additional_args="--variant variant.arch=%s" % "sparc")
                self.pkg("install silver", exit=1)

        def __vtest(self, depot, arch, zone, isdebug=""):
                """ test if install works for spec'd arch"""

                if isdebug:
                        do_isdebug = "--variant variant.debug.kernel=%s" % isdebug
                else:
                        do_isdebug = ""
                        is_debug = "false"

                self.image_create(depot, 
                    additional_args="--variant variant.arch=%s --variant variant.opensolaris.zone=%s %s" % (
                    arch, zone, do_isdebug))
                self.pkg("install bronze")
                self.pkg("verify")
                self.file_contains("etc/motd", arch)
                self.file_contains("etc/zone_motd", zone)
                self.file_contains("etc/zone_arch", zone)
                self.file_contains("etc/zone_arch", arch)
                self.file_contains("etc/isdebug", isdebug)
                self.image_destroy()

        def file_contains(self, path, string):
                file_path = os.path.join(self.get_img_path(), path)
                try:
                        f = file(file_path)
                except:
                        self.assert_(False, "File %s is missing" % path)
                for line in f:
                        if string in line:
                                f.close()
                                break
                else:
                        f.close()
                        self.assert_(False, "File %s does not contain %s" % (path, string))

if __name__ == "__main__":
        unittest.main()
