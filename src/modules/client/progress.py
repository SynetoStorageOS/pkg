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

#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys
import os
import time

class ProgressTracker(object):
        """ This abstract class is used by the client to render and track
            progress towards the completion of various tasks, such as
            download, installation, update, etc.

            The superclass is largely concerned with tracking the
            raw numbers, and with calling various callback routines
            when events of interest occur.

            Different subclasses provide the actual rendering to the
            user, with differing levels of detail and prettiness.

            Note that as currently envisioned, this class is concerned
            with tracking the progress of long-running operations: it is
            NOT a general purpose output mechanism nor an error collector.

            Subclasses must implement all of the *_output_* methods.
        """

        def __init__(self):
                self.cat_cur_catalog = None

                self.ver_cur_fmri = None

                self.dl_goal_nfiles = 0
                self.dl_cur_nfiles = 0
                self.dl_goal_nbytes = 0
                self.dl_cur_nbytes = 0
                self.dl_goal_npkgs = 0
                self.dl_cur_npkgs = 0
                self.dl_cur_pkg = "None"

                self.act_cur_nactions = 0
                self.act_goal_nactions = 0
		self.act_phase = "None"
		self.act_phase_last = "None"

                self.debug = False
                self.last_printed = 0 # when did we last emit status?

        def catalog_start(self, catalog):
                self.cat_cur_catalog = catalog
                self.cat_output_start()

        def catalog_done(self):
                self.cat_output_done()

        def evaluate_start(self):
                self.eval_output_start()

        def evaluate_done(self):
                self.eval_output_done()

        def verify_add_progress(self, fmri):
                self.ver_cur_fmri = fmri
                self.ver_output()

        def verify_yield_error(self, actname, errors):
                self.ver_output_error(actname, errors)

        def verify_done(self):
                self.ver_cur_fmri = None
                self.ver_output()

        def download_set_goal(self, npkgs, nfiles, nbytes):
                self.dl_goal_npkgs = npkgs
                self.dl_goal_nfiles = nfiles
                self.dl_goal_nbytes = nbytes

        def download_start_pkg(self, pkgname):
                self.dl_cur_pkg = pkgname
                if self.dl_goal_nbytes != 0:
                        self.dl_output()

        def download_end_pkg(self):
                self.dl_cur_npkgs += 1
                if self.dl_goal_nbytes != 0:
                        self.dl_output()

        def download_add_progress(self, nfiles, nbytes):
                """ Call to provide news that the download has made progress """

                self.dl_cur_nbytes += nbytes
                self.dl_cur_nfiles += nfiles
                if self.dl_goal_nbytes != 0:
                        self.dl_output()

        def download_done(self):
                """ Call when all downloading is finished """
                if self.dl_goal_nbytes != 0:
                        self.dl_output_done()
                assert self.dl_cur_npkgs == self.dl_goal_npkgs
                assert self.dl_cur_nfiles == self.dl_goal_nfiles
                assert self.dl_cur_nbytes == self.dl_goal_nbytes

        def download_get_progress(self):
                return (self.dl_cur_npkgs, self.dl_cur_nfiles, self.dl_cur_nbytes)

        def actions_set_goal(self, phase, nactions):
                self.act_phase = phase
                self.act_goal_nactions = nactions
		self.act_cur_nactions = 0

        def actions_add_progress(self):
                self.act_cur_nactions += 1
                if self.act_goal_nactions > 0:
                        self.act_output()

        def actions_done(self):
                if self.act_goal_nactions > 0:
                        self.act_output_done()
                assert self.act_goal_nactions == self.act_cur_nactions

        def actions_get_progress(self):
                print "not yet"

        #
        # This set of methods should be regarded as abstract *and* protected.
        # If you aren't in this class hierarchy, these should not be
        # called directly.  Subclasses should implement all of these methods.
        #
        def cat_output_start(self):
                raise NotImplementedError("cat_output_start() not implemented in superclass")

        def cat_output_done(self):
                raise NotImplementedError("cat_output_done() not implemented in superclass")

        def eval_output_start(self):
                raise NotImplementedError("eval_output_start() not implemented in superclass")

        def eval_output_done(self):
                raise NotImplementedError("eval_output_done() not implemented in superclass")

        def ver_output(self):
                raise NotImplementedError("ver_output() not implemented in superclass")

        def ver_output_error(self, actname, errors):
                raise NotImplementedError("ver_output_error() not implemented in superclass")

        def dl_output(self):
                raise NotImplementedError("dl_output() not implemented in superclass")

        def dl_output_done(self):
                raise NotImplementedError("dl_output_done() not implemented in superclass")

        def act_output(self):
                raise NotImplementedError("act_output() not implemented in superclass")

        def act_output_done(self):
                raise NotImplementedError("act_output_done() not implemented in superclass")



class ProgressTrackerException(Exception):
        """ This exception is currently thrown if a ProgressTracker determines
            that it can't be instantiated; for example, the tracker which
            depends on a UNIX style terminal should throw this exception
            if it can't find a valid terminal. """

        def __init__(self):
                Exception.__init__(self)



class QuietProgressTracker(ProgressTracker):
        """ This progress tracker outputs nothing, but is semantically
            intended to be "quiet"  See also NullProgressTracker below """

        def __init__(self):
                ProgressTracker.__init__(self)

        def cat_output_start(self): return

        def cat_output_done(self): return

        def eval_output_start(self): return

        def eval_output_done(self): return

        def ver_output(self): return

        def ver_output_error(self, actname, errors): return

        def dl_output(self): return

        def dl_output_done(self): return

        def act_output(self): return

        def act_output_done(self): return


class NullProgressTracker(QuietProgressTracker):
        """ This ProgressTracker is a subclass of QuietProgressTracker
            because that's convenient for now.  It is semantically intended to
            be a no-op progress tracker, and is useful for short-running
            operations which need not display progress of any kind. """

        def __init__(self):
                QuietProgressTracker.__init__(self)


class CommandLineProgressTracker(ProgressTracker):
        """ This progress tracker is a generically useful tracker for
            command line output.  It needs no special terminal features
            and so is appropriate for sending through a pipe.  This code
            is intended to be platform neutral. """

        def __init__(self):
                ProgressTracker.__init__(self)
                self.dl_last_printed_pkg = None

        def cat_output_start(self): return

        def cat_output_done(self): return

        def eval_output_start(self): return

        def eval_output_done(self): return

        def ver_output(self): return

        def ver_output_error(self, actname, errors): return

        def dl_output(self):
                # The first time, emit header.
                if self.dl_cur_pkg != self.dl_last_printed_pkg:
                        if self.dl_last_printed_pkg != None:
                                print "Done"
                        print "Download: %s ... " % (self.dl_cur_pkg),
                        self.dl_last_printed_pkg = self.dl_cur_pkg
                sys.stdout.flush()

        def dl_output_done(self):
                print "Done"
                sys.stdout.flush()

        def act_output(self):
		if self.act_phase != self.act_phase_last:
			print "%s ... " % self.act_phase,
			self.act_phase_last = self.act_phase
                return

        def act_output_done(self):
                print "Done"
                sys.stdout.flush()



class FancyUNIXProgressTracker(ProgressTracker):
        """ This progress tracker is designed for UNIX-like OS's--
            those which have UNIX-like terminal semantics.  It attempts
            to load the 'curses' package.  If that or other terminal-liveness
            tests fail, it gives up: the client should pick some other more
            suitable tracker.  (Probably CommandLineProgressTracker). """

        def __init__(self):
                ProgressTracker.__init__(self)

                self.act_started = False
                self.last_print_time = 0

                try:
                        import curses
                        if not os.isatty(sys.stdout.fileno()):
                                raise ProgressTrackerException()

                        curses.setupterm()
                        self.cr = curses.tigetstr("cr")
                except:
                        raise ProgressTrackerException()
                self.dl_started = False
                self.spinner = 0
                self.spinner_chars = "/-\|"
		self.cat_curstrlen = 0

        def cat_output_start(self):
                catstr = "Fetching catalog '%s'..." % (self.cat_cur_catalog)
                self.cat_curstrlen = len(catstr)
                print "%s" % catstr,
                sys.stdout.flush()

        def cat_output_done(self):
                print self.cr,
                print ("%" + str(self.cat_curstrlen) + "s") % "",
                print self.cr,
                sys.stdout.flush()

        def eval_output_start(self):
                s = "Creating Plan"
                self.cat_curstrlen = len(s)
                print "%s" % s,
                sys.stdout.flush()

        def eval_output_done(self):
                print self.cr,
                print ("%" + str(self.cat_curstrlen) + "s") % "",
                print self.cr,
                sys.stdout.flush()

        def ver_output(self):
                print self.cr,
                if self.ver_cur_fmri != None:
                        if (time.time() - self.last_print_time) >= 0.10:
                                self.last_print_time = time.time()
                        else:
                                return
                        self.spinner += 1
                        if self.spinner >= len(self.spinner_chars):
                                self.spinner = 0
                        print "%-50s..... %c%c" % \
			    (self.ver_cur_fmri.get_pkg_stem(), 
			     self.spinner_chars[self.spinner],
			     self.spinner_chars[self.spinner]),
                        print self.cr,
                        sys.stdout.flush()
                else:
                        print "%80s" % "",
                        sys.stdout.flush()
                        self.last_print_time = 0

        def ver_output_error(self, actname, errors):
                # for now we just get the "Verifying" progress
                # thingy out of the way.
                print "%40s" % "",
                print self.cr,
                sys.stdout.flush()

        def dl_output(self):
                # The first time, emit header.
                if not self.dl_started:
                        self.dl_started = True
                        print "%-40s %7s %11s %13s" % ("DOWNLOAD", \
                            "PKGS", "FILES", "XFER (MB)")
                else:
                        print self.cr,
                print "%-40s %7s %11s %13s" % \
                    (self.dl_cur_pkg,
                    "%d/%d" % (self.dl_cur_npkgs, self.dl_goal_npkgs),
                    "%d/%d" % (self.dl_cur_nfiles, self.dl_goal_nfiles),
                    "%.2f/%.2f" % ((self.dl_cur_nbytes / 1024.0 / 1024.0),
                       (self.dl_goal_nbytes / 1024.0 / 1024.0))),
                sys.stdout.flush()

        def dl_output_done(self):
                self.dl_cur_pkg = "Completed"
                self.dl_output()
                print
                print
                sys.stdout.flush()

        def act_output(self, force = False):
                if force or (time.time() - self.last_print_time) >= 0.05:
                        self.last_print_time = time.time()
                else:
                        return

                # The first time, emit header.
                if not self.act_started:
                        self.act_started = True
			print "%-40s %11s" % ("PHASE", "ACTIONS")
                else:
                        print self.cr,

                print "%-40s %11s" % \
                    (
			self.act_phase,
			"%d/%d" % (self.act_cur_nactions, self.act_goal_nactions)
		     ),

                sys.stdout.flush()

        def act_output_done(self):
		self.act_output(force=True)
                print
                sys.stdout.flush()
