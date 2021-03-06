#!/usr/bin/python
# Copyright (c) 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009 Python
# Software Foundation; All Rights Reserved
#
# Copyright (c) 2010, 2011, Oracle and/or its affiliates. All rights reserved.


"""A standalone version of ModuleFinder which limits the depth of exploration
for loaded modules and discovers where a module might be loaded instead of
determining which path contains a module to be loaded.  It is designed to be run
by python2.4 against 2.4 modules.  To communicate its results to the process
which ran it, it prints output to stdout.  The format is to start a line with
'DEP ' if it contains information about a dependency, and 'ERR ' if it contains
information about a module it couldn't analyze."""

# This module cannot import other pkg modules because running the 2.4
# interpreter will overwrite the pyc files for some of the other flavor modules.
# With 2.6, the -B option can be added to the command line invocation for the
# subprocess and the interpreter won't overwrite pyc files.

import dis
import modulefinder
import os
import sys

from modulefinder import LOAD_CONST, IMPORT_NAME, STORE_NAME, STORE_GLOBAL, \
    STORE_OPS

# A string used as a component of the pkg.depend.runpath value as a special
# token to determine where to insert the runpath that pkgdepend generates itself
# (duplicated from pkg.portable.__init__ for reasons above)
PD_DEFAULT_RUNPATH = "$PKGDEPEND_RUNPATH"

python_path = "PYTHONPATH"

class ModuleInfo(object):
        """This class contains information about from where a python module
        might be loaded."""

        def __init__(self, name, dirs, builtin=False):
                """Build a ModuleInfo object.

                The 'name' parameter is the name of the module.

                The 'dirs' parameter is the list of directories where the module
                might be found.

                The 'builtin' parameter sets whether the module is a python
                builtin (like sys)."""

                self.name = name
                self.builtin = builtin
                self.suffixes = [".py", ".pyc", ".pyo", "/__init__.py", ".so",
                    "module.so"]
                self.dirs = sorted(dirs)

        def make_package(self):
                """Declare that this module is a package."""

                if self.dirs:
                        self.suffixes = ["/__init__.py"]
                else:
                        self.suffixes = []

        def get_package_dirs(self):
                """Get the directories where this package might be defined."""

                return [os.path.join(p, self.name) for p in self.dirs]

        def get_file_names(self):
                """Return all the file names under which this module might be
                found."""

                return ["%s%s" % (self.name, suf) for suf in self.suffixes]

        def __str__(self):
                return "name:%s suffixes:%s dirs:%s" % (self.name,
                    " ".join(self.suffixes), len(self.dirs))

class MultipleDefaultRunPaths(Exception):

        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
                return str(self)

        def __str__(self):
                return _(
                    "More than one $PKGDEPEND_RUNPATH token was set on the "
                    "same action in this manifest.")

class DepthLimitedModuleFinder(modulefinder.ModuleFinder):

        def __init__(self, install_dir, *args, **kwargs):
                """Produce a module finder that ignores PYTHONPATH and only
                reports the direct imports of a module.

                run_paths as a keyword argument specifies a list of additional
                paths to use when searching for modules."""

                # ModuleFinder.__init__ doesn't expect run_paths
                run_paths = kwargs.pop("run_paths", [])

                # Check to see whether a python path has been set.
                if python_path in os.environ:
                        py_path = [
                            os.path.normpath(fp)
                            for fp in os.environ[python_path].split(os.pathsep)
                        ]
                else:
                        py_path = []

                # Remove any paths that start with the defined python paths.
                new_path = [
                    fp
                    for fp in sys.path[1:]
                    if not self.startswith_path(fp, py_path)
                ]
                new_path.append(install_dir)

                if run_paths:
                        # insert our default search path where the
                        # PD_DEFAULT_RUNPATH token was found
                        try:
                                index = run_paths.index(PD_DEFAULT_RUNPATH)
                                if index >= 0:
                                        run_paths = run_paths[:index] + \
                                            new_path + run_paths[index + 1:]
                                if PD_DEFAULT_RUNPATH in run_paths:
                                        raise MultipleDefaultRunPaths()
                        except ValueError:
                                # no PD_DEFAULT_PATH token, so we override the
                                # whole default search path
                                pass
                        new_path = run_paths

                modulefinder.ModuleFinder.__init__(self, path=new_path,
                    *args, **kwargs)

        @staticmethod
        def startswith_path(path, lst):
                for l in lst:
                        if path.startswith(l):
                                return True
                return False

        def run_script(self, pathname):
                """Find all the modules the module at pathname directly
                imports."""

                fp = open(pathname, "r")
                return self.load_module('__main__', fp, pathname)

        def load_module(self, fqname, fp, pathname):
                """This code has been slightly modified from the function of
                the parent class. Specifically, it checks the current depth
                of the loading and halts if it exceeds the depth that was given
                to run_script."""

                self.msgin(2, "load_module", fqname, fp and "fp", pathname)
                co = compile(fp.read()+'\n', pathname, 'exec')
                m = self.add_module(fqname)
                m.__file__ = pathname
                res = []
                if co:
                        if self.replace_paths:
                                co = self.replace_paths_in_code(co)
                        m.__code__ = co
                        try:
                                res.extend(self.scan_code(co, m))
                        except ImportError, msg:
                                self.msg(2, "ImportError:", str(msg), fqname,
                                    pathname)
                                self._add_badmodule(fqname, m)
                self.msgout(2, "load_module ->", m)
                return res

        def scan_code(self, co, m):
                res = []
                code = co.co_code
                n = len(code)
                i = 0
                fromlist = None
                while i < n:
                        c = code[i]
                        i = i+1
                        op = ord(c)
                        if op >= dis.HAVE_ARGUMENT:
                                oparg = ord(code[i]) + ord(code[i+1])*256
                                i = i+2
                        if op == LOAD_CONST:
                                # An IMPORT_NAME is always preceded by a
                                # LOAD_CONST, it's a tuple of "from" names, or
                                # None for a regular import.  The tuple may
                                # contain "*" for "from <mod> import *"
                                fromlist = co.co_consts[oparg]
                        elif op == IMPORT_NAME:
                                assert fromlist is None or \
                                    type(fromlist) is tuple
                                name = co.co_names[oparg]
                                have_star = 0
                                if fromlist is not None:
                                        if "*" in fromlist:
                                                have_star = 1
                                        fromlist = [
                                            f for f in fromlist if f != "*"
                                        ]
                                res.extend(self._safe_import_hook(name, m,
                                    fromlist))
                        elif op in STORE_OPS:
                                # keep track of all global names that are
                                # assigned to
                                name = co.co_names[oparg]
                                m.globalnames[name] = 1
                for c in co.co_consts:
                    if isinstance(c, type(co)):
                        res.extend(self.scan_code(c, m))
                return res


        def _safe_import_hook(self, name, caller, fromlist, level=-1):
                """Wrapper for self.import_hook() that won't raise ImportError.
                """

                res = []
                if name in self.badmodules:
                        self._add_badmodule(name, caller)
                        return []
                try:
                        res.extend(self.import_hook(name, caller, level=level))
                except ImportError, msg:
                        self.msg(2, "ImportError:", str(msg))
                        self._add_badmodule(name, caller)
                else:
                        if fromlist:
                                for sub in fromlist:
                                        if sub in self.badmodules:
                                                self._add_badmodule(sub, caller)
                                                continue
                                        res.extend(self.import_hook(name,
                                            caller, [sub], level=level))
                return res

        def import_hook(self, name, caller=None, fromlist=None, level=-1):
                """Find all the modules that importing name will import."""

                # Special handling for os.path is needed because the os module
                # manipulates sys.modules directly to provide both os and
                # os.path.
                if name == "os.path":
                        self.msg(2, "bypassing os.path import - importing os "
                            "instead", name, caller, fromlist, level)
                        name = "os"

                self.msg(3, "import_hook", name, caller, fromlist, level)
                parent = self.determine_parent(caller)
                q, tail = self.find_head_package(parent, name)
                if not tail:
                        # If q is a builtin module, don't report it because it
                        # doesn't live in the normal module space and it's part
                        # of python itself, which is handled by a different
                        # kind of dependency.
                        if isinstance(q, ModuleInfo) and q.builtin:
                                return []
                        elif isinstance(q, modulefinder.Module):
                                name = q.__name__
                                path = q.__path__
                                # some Module objects don't get a path, this
                                # isn't optimal, but it's the best we can do
                                if not path:
                                        if name in sys.builtin_module_names or \
                                            name == "__future__":
                                                return [ModuleInfo(name, [],
                                                    builtin=True)]
                                        else:
                                                return [ModuleInfo(name, [])]
                                return [ModuleInfo(name, path)]
                        else:
                                return [q]
                res = self.load_tail(q, tail)
                q.make_package()
                res.append(q)
                return res

        def import_module(self, partname, fqname, parent):
                """Find where this module lives relative to its parent."""

                parent_dirs = None
                self.msgin(3, "import_module", partname, fqname, parent)
                try:
                        m = self.modules[fqname]
                except KeyError:
                        pass
                else:
                        self.msgout(3, "import_module ->", m)
                        return m
                if fqname in self.badmodules:
                        self.msgout(3, "import_module -> None")
                        return None
                if parent:
                        if not parent.dirs:
                                self.msgout(3, "import_module -> None")
                                return None
                        else:
                                parent_dirs = parent.get_package_dirs()
                try:
                        mod = self.find_module(partname, parent_dirs, parent)
                except ImportError:
                        self.msgout(3, "import_module ->", None)
                        return None
                return mod

        def find_module(self, name, path, parent=None):
                """Calculate the potential paths on the file system where the
                module could be found."""

                if path is None:
                    if name in sys.builtin_module_names or name == "__future__":
                            return ModuleInfo(name, [], builtin=True)
                    path = self.path
                return ModuleInfo(name, path)

        def load_tail(self, q, tail):
                """Determine where each component of a multilevel import would
                be found on the file system."""

                self.msgin(4, "load_tail", q, tail)
                res = []
                name = q.name
                cur_parent = q
                while tail:
                        i = tail.find('.')
                        if i < 0: i = len(tail)
                        head, tail = tail[:i], tail[i+1:]
                        new_name = "%s.%s" % (name, head)
                        r = self.import_module(head, new_name, cur_parent)
                        res.append(r)
                        name = new_name
                        cur_parent = r

                # All but the last module found must be packages because they
                # contained other packages.
                for i in range(0, len(res) - 1):
                        res[i].make_package()

                self.msgout(4, "load_tail ->", q)
                return res


if __name__ == "__main__":
        """Usage:
              depthlimitedmf24.py <install_path> <script>
                  [ run_path run_path ... ]
        """
        run_paths = sys.argv[3:]
        try:
                mf = DepthLimitedModuleFinder(sys.argv[1], run_paths=run_paths)
                loaded_modules = mf.run_script(sys.argv[2])
                for res in set([
                    (tuple(m.get_file_names()), tuple(m.dirs))
                    for m in loaded_modules
                ]):
                        print "DEP %s" % (res,)
                missing, maybe =  mf.any_missing_maybe()
                for name in missing:
                        print "ERR %s" % name,
        except ValueError, e:
                print "ERR %s" % e
        except MultipleDefaultRunPaths, e:
                print e
