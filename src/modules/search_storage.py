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

# need to add locks to the dictionary reading so that we don't have
# multiple threads loading in the dictionary at the same time

import os
import errno
import time
import stat

import pkg.fmri as fmri
import pkg.search_errors as search_errors
import pkg.portable as portable

def consistent_open(data_list, directory, timeout = None):
        """Opens all data holders in data_list and ensures that the
        versions are consistent among all of them.
        It retries several times in case a race condition between file
        migration and open is encountered.
        Note: Do not set timeout to be 0. It will cause an exception to be
        immediately raised.

        """
        missing = None
        cur_version = None

        start_time = time.time()

        while cur_version == None and missing != True:
                # The assignments to cur_version and missing cannot be
                # placed here. They must be reset prior to breaking out of the
                # for loop so that the while loop condition will be true. They
                # cannot be placed after the for loop since that path is taken
                # when all files are missing or opened successfully.
                if timeout != None and ((time.time() - start_time) > timeout):
                        raise search_errors.InconsistentIndexException(
                            directory)
                for d in data_list:
                        # All indexes must have the same version and all must
                        # either be present or absent for a successful return.
                        # If one of these conditions is not met, the function
                        # tries again until it succeeds or the time spent in
                        # in the function is greater than timeout.
                        try:
                                f = os.path.join(directory, d.get_file_name())
                                fh = open(f, 'rb')
                                # If we get here, then the current index file
                                # is present.
                                if missing == None:
                                        missing = False
                                elif missing:
                                        for dl in data_list:
                                                dl.close_file_handle()
                                        missing = None
                                        cur_version = None
                                        break
                                d.set_file_handle(fh, f)
                                version_tmp = fh.next()
                                version_num = \
                                    int(version_tmp.split(' ')[1].rstrip('\n'))
                                # Read the version. If this is the first file,
                                # set the expected version otherwise check that
                                # the version matches the expected version.
                                if cur_version == None:
                                        cur_version = version_num
                                elif not (cur_version == version_num):
                                        # Got inconsistent versions, so close
                                        # all files and try again.
                                        for d in data_list:
                                                d.close_file_handle()
                                        missing = None
                                        cur_version = None
                                        break
                        except IOError, e:
                                if e.errno == errno.ENOENT:
                                        # If the index file is missing, ensure
                                        # that previous files were missing as
                                        # well. If not, try again.
                                        if missing == False:
                                                for d in data_list:
                                                        d.close_file_handle()
                                                missing = None
                                                cur_version = None
                                                break
                                        missing = True
                                else:
                                        for d in data_list:
                                                d.close_file_handle()
                                        raise
        if missing:
                assert cur_version == None
                # The index is missing (ie, no files were present).
                return None
        else:
                assert cur_version is not None
                return cur_version


class IndexStoreBase(object):
        """Base class for all data storage used by the indexer and
        queryEngine. All members must have a file name and maintain
        an internal file handle to that file as instructed by external
        calls.
        """

        def __init__(self, file_name):
                self._name = file_name
                self._file_handle = None
                self._file_path = None
                self._size = None
                self._mtime = None

        def get_file_name(self):
                return self._name

        def set_file_handle(self, f_handle, f_path):
                if self._file_handle:
                        raise RuntimeError("setting an extant file handle, "
                            "must close first, fp is: " + f_path)
                else:
                        self._file_handle = f_handle
                        self._file_path = f_path

        def get_file_path(self):
                return self._file_path

        def close_file_handle(self):
                """Closes the file handle and clears it so that it cannot
                be reused.
                """
                if self._file_handle:
                        self._file_handle.close()
                        self._file_handle = None
                        self._file_path = None

        def _protected_write_dict_file(self, path, version_num, iterable):
                """Writes the dictionary in the expected format.
                Note: Only child classes should call this method.
                """
                version_string = "VERSION: "
                file_handle = open(os.path.join(path, self._name), 'wb')
                file_handle.write(version_string + str(version_num) + "\n")
                for name in iterable:
                        file_handle.write(str(name) + "\n")
                file_handle.close()

        def should_reread(self):
                """This method uses the modification time and the file size
                to (heuristically) determine whether the file backing this
                storage has changed since it was last read.
                """
                stat_info = os.stat(self._file_path)
                if self._mtime != stat_info.st_mtime or \
                    self._size != stat_info.st_size:
                        self._mtime = stat_info[stat.ST_MTIME]
                        self._size = stat_info[stat.ST_SIZE]
                        return True
                return False

        def open(self, directory):
                """This uses consistent open to ensure that the version line
                processing is done consistently and that only a single function
                actually opens files stored using this class.
                """
                return consistent_open([self], directory)


class IndexStoreMainDict(IndexStoreBase):
        """Class for representing the main dictionary file
        """
        # Here is an example of a line from the main dictionary, it is
        # explained below:
        # %gconf.xml (5,3,65689 => 249,202) (5,3,65690 => 249,202)
        # (5,3,65691 => 249,202) (5,3,65692 => 249,202)
        #
        # The main dictionary has a more complicated format. Each line begins
        # with a search token (%gconf.xml) followed by a list of mappings. Each
        # mapping takes a token_type, action, and keyvalue tuple ((5,3,65689),
        # (5,3,65690), (5,3,65691), (5,3,65692)) to a list of pkg-stem, version
        # pairs (249,202) in which the token is found in an action with
        # token_type, action, and keyvalues matching the tuple. Further
        # compaction is gained by storing everything but the token as an id
        # which the other dictionaries can turn into human-readable content.
        #
        # In short, the definition of a main dictionary entry is:
        # Note: "(", ")", and "=>" actually appear in the file
        #       "[", "]", and "+" are used to specify pattern
        # token [(token_type_id, action_id, keyval_id => [pkg_stem_id,version_id ]+)]+

        def __init__(self, file_name):
                IndexStoreBase.__init__(self, file_name)
                self._old_suffix = None

        def write_dict_file(self, path, version_num):
                """This class relies on external methods to write the file.
                Making this empty call to protected_write_dict_file allows the
                file to be set up correctly with the version number stored
                correctly.
                """
                IndexStoreBase._protected_write_dict_file(self, path,
                                                          version_num, [])

        def get_file_handle(self):
                """Return the file handle. Note that doing
                anything other than sequential reads or writes
                to or from this file_handle may result in unexpected
                behavior. In short, don't use seek.
                """
                return self._file_handle

        @staticmethod
        def parse_main_dict_line(line):
                """Parses one line of a main dictionary file.
                Changes to this function must be paired with changes to
                write_main_dict_line below.
                """
                line = line.rstrip('\n')
                tok_end = line.find(' ')
                assert tok_end > 0
                tok = line[:tok_end]
                entries = line[tok_end + 2:].split('(')
                res = []
                for entry in entries:
                        tup, lst = entry.split('=>')
                        fmri_ids_text = lst.strip()
                        fmri_ids = fmri_ids_text.split(' ')
                        fmri_ids[len(fmri_ids) - 1] = \
                            fmri_ids[len(fmri_ids) - 1].strip(')')
                        tok_type_id, action_id, keyval_id = tup.split(',')
                        tok_type_id = int(tok_type_id)
                        action_id = int(action_id)
                        keyval_id = int(keyval_id)
                        processed_fmris = []
                        for label in fmri_ids:
                                fmri_id, version_id = label.split(',')
                                fmri_id = int(fmri_id)
                                version_id = int(version_id)
                                processed_fmris.append((fmri_id, version_id))
                        res.append((tok_type_id, action_id, keyval_id,
                            processed_fmris))
                return (tok, res)

        @staticmethod
        def write_main_dict_line(file_handle, token, dictionary):
                """Paired with parse_main_dict_line above. Writes
                a line in a main dictionary file in the appropriate format.
                """
                file_handle.write(token)
                for k in dictionary.keys():
                        tok_type_id, action_id, keyval_id = k
                        file_handle.write(" (" + str(tok_type_id) +
                                          "," + str(action_id) + "," +
                                          str(keyval_id) + " =>")
                        tmp_list = list(dictionary[k])
                        tmp_list.sort()
                        for pkg_id, version_id in tmp_list:
                                file_handle.write(" " + str(pkg_id) + "," +
                                                  str(version_id))
                        file_handle.write(")")
                file_handle.write("\n")

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing.
                """
                # This returns 0 because this class is not responsible for
                # storing anything in memory.
                return 0

        def shift_file(self, use_dir, suffix):
                """Moves the existing file with self._name in directory
                use_dir to a new file named self._name + suffix in directory
                use_dir. If it has done this previously, it removes the old
                file it moved. It also opens the newly moved file and uses
                that as the file for its file handle.
                """
                assert self._file_handle is None
                orig_path = os.path.join(use_dir, self._name)
                new_path = os.path.join(use_dir, self._name + suffix)
                portable.rename(orig_path, new_path)
                tmp_name = self._name
                self._name = self._name + suffix
                self.open(use_dir)
                self._name = tmp_name
                if self._old_suffix is not None:
                        os.remove(os.path.join(use_dir, self._old_suffix))
                self._old_suffix = self._name + suffix


class IndexStoreListDict(IndexStoreBase):
        """Used when both a list and a dictionary are needed to
        store the information. Used for bidirectional lookup when
        one item is an int (an id) and the other is not (an entity). It
        maintains a list of empty spots in the list so that adding entities
        can take advantage of unused space. It encodes empty space as a blank
        line in the file format and '' in the internal list.
        """

        def __init__(self, file_name, build_function=None):
                IndexStoreBase.__init__(self, file_name)
                self._list = []
                self._dict = {}
                self._next_id = 0
                self._list_of_empties = []
                self._build_func = build_function
                self._line_cnt = 0

        def add_entity(self, entity, is_empty):
                """Adds an entity consistently to the list and dictionary
                allowing bidirectional lookup.
                """
                assert (len(self._list) == self._next_id)
                if self._list_of_empties and not is_empty:
                        use_id = self._list_of_empties.pop(0)
                        assert use_id <= len(self._list)
                        if use_id == len(self._list):
                                self._list.append(entity)
                                self._next_id += 1
                        else:
                                self._list[use_id] = entity
                else:
                        use_id = self._next_id
                        self._list.append(entity)
                        self._next_id += 1
                if not(is_empty):
                        self._dict[entity] = use_id
                assert (len(self._list) == self._next_id)
                return use_id

        def remove_id(self, in_id):
                """deletes in_id from the list and the dictionary """
                entity = self._list[in_id]
                self._list[in_id] = ""
                self._dict[entity] = ""

        def remove_entity(self, entity):
                """deletes the entity from the list and the dictionary """
                in_id = self._dict[entity]
                self._dict[entity] = ""
                self._list[in_id] = ""

        def get_id(self, entity):
                """returns the id of entity """
                return self._dict[entity]

        def get_id_and_add(self, entity):
                """Adds entity if it's not previously stored and returns the
                id for entity. 
                """
                # This code purposefully reimplements add_entity
                # code. Replacing the function calls to has_entity, add_entity,
                # and get_id with direct access to the data structure gave a
                # speed up of a factor of 4. Because this is a very hot path,
                # the tradeoff seemed appropriate.

                if not self._dict.has_key(entity):
                        assert (len(self._list) == self._next_id)
                        if self._list_of_empties:
                                use_id = self._list_of_empties.pop(0)
                                assert use_id <= len(self._list)
                                if use_id == len(self._list):
                                        self._list.append(entity)
                                        self._next_id += 1
                                else:
                                        self._list[use_id] = entity
                        else:
                                use_id = self._next_id
                                self._list.append(entity)
                                self._next_id += 1
                        self._dict[entity] = use_id
                assert (len(self._list) == self._next_id)
                return self._dict[entity]

        def get_entity(self, in_id):
                """return the entity in_id maps to """
                return self._list[in_id]

        def has_entity(self, entity):
                """check if entity is in storage """
                return self._dict.has_key(entity)

        def has_empty(self):
                """Check if the structure has any empty elements which
                can be filled with data.
                """
                return (len(self._list_of_empties) > 0)

        def get_next_empty(self):
                """returns the next id which maps to no element """
                return self._list_of_empties.pop()

        def write_dict_file(self, path, version_num):
                """Passes self._list to the parent class to write to a file.
                """
                IndexStoreBase._protected_write_dict_file(self, path,
                                                          version_num,
                                                          self._list)

        def read_dict_file(self):
                """Reads in a dictionary previously stored using the above
                call
                """
                assert self._file_handle
                if self.should_reread():
                        self._dict.clear()
                        self._list = []
                        for i, line in enumerate(self._file_handle):
                                # A blank line means that id can be reused.
                                tmp = line.rstrip('\n')
                                if line == '\n':
                                        self._list_of_empties.append(i)
                                else:
                                        if self._build_func:
                                                tmp = self._build_func(tmp)
                                        self._dict[tmp] = i
                                self._list.append(tmp)
                                self._line_cnt = i + 1
                                self._next_id = i + 1
                return self._line_cnt

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing.
                """
                return len(self._list)

class IndexStoreDict(IndexStoreBase):
        """Class used when only entity -> id lookup is needed
        """

        def __init__(self, file_name):
                IndexStoreBase.__init__(self, file_name)
                self._dict = {}
                self._next_id = 0

        def get_dict(self):
                return self._dict

        def get_entity(self, in_id):
                return self._dict[in_id]

        def has_entity(self, entity):
                return self._dict.has_key(entity)

        def read_dict_file(self):
                """Reads in a dictionary stored in line number -> entity
                format
                """
                if self.should_reread():
                        self._dict.clear()
                        for line_cnt, line in enumerate(self._file_handle):
                                line = line.rstrip('\n')
                                self._dict[line_cnt] = line

        def matching_read_dict_file(self, in_set):
                """If it's necessary to reread the file, it rereads the
                file. It matches the line it reads against the contents of
                in_set. If a match is found, the entry on the line is stored
                for later use, otherwise the line is skipped. When all items
                in in_set have been matched, the method is done and returns.
                """
                if self.should_reread():
                        self._dict.clear()
                        match_cnt = 0
                        max_match = len(in_set)
                        for i, line in enumerate(self._file_handle):
                                if i in in_set:
                                        match_cnt += 1
                                        line = line.rstrip('\n')
                                        self._dict[i] = line
                                if match_cnt >= max_match:
                                        break

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing.
                """
                return len(self._dict)

class IndexStoreDictMutable(IndexStoreBase):
        """Dictionary which allows dynamic update of its storage
        """

        def __init__(self, file_name):
                IndexStoreBase.__init__(self, file_name)
                self._dict = {}

        def get_dict(self):
                return self._dict

        def has_entity(self, entity):
                return self._dict.has_key(entity)

        def get_id(self, entity):
                return self._dict[entity]

        def read_dict_file(self):
                """Reads in a dictionary stored in with an entity
                and its number on each line.
                """
                if self.should_reread():
                        self._dict.clear()
                        for line in self._file_handle:
                                res = line.split()
                                token = res[0]
                                offset = int(res[1])
                                self._dict[token] = offset

        def open_out_file(self, use_dir, version_num):
                """Opens the output file for this class and prepares it
                to be written via write_entity.
                """

                IndexStoreBase._protected_write_dict_file(self, use_dir,
                    version_num, [])
                self._file_handle = open(os.path.join(use_dir, self._name),
                    'ab')

        def write_entity(self, entity, my_id):
                """Writes the entity out to the file with my_id """
                assert self._file_handle is not None
                self._file_handle.write(str(entity) + " " + str(my_id) + "\n")

        def write_dict_file(self, path, version_num):
                """ Generates an iterable list of string representations of
                the dictionary that the parent's protected_write_dict_file
                function can call.
                """
                IndexStoreBase._protected_write_dict_file(self, path,
                    version_num, [])

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing.
                """
                return 0

class IndexStoreSet(IndexStoreBase):
        """Used when only set membership is desired.
        This is currently designed for exclusive use
        with storage of fmri.PkgFmris. However, that impact
        is only seen in the read_and_discard_matching_from_argument
        method.
        """
        def __init__(self, file_name):
                IndexStoreBase.__init__(self, file_name)
                self._set = set()

        def get_set(self):
                return self._set

        def add_entity(self, entity):
                self._set.add(entity)

        def remove_entity(self, entity):
                """Remove entity purposfully assumes that entity is
                already in the set to be removed. This is useful for
                error checking and debugging.
                """
                self._set.remove(entity)

        def has_entity(self, entity):
                return (entity in self._set)

        def write_dict_file(self, path, version_num):
                """Write each member of the set out to a line in a file """
                IndexStoreBase._protected_write_dict_file(self, path,
                    version_num, self._set)

        def read_dict_file(self):
                """Process a dictionary file written using the above method
                """
                assert self._file_handle
                res = 0
                if self.should_reread():
                        self._set.clear()
                        for i, line in enumerate(self._file_handle):
                                line = line.rstrip('\n')
                                assert i == len(self._set)
                                self.add_entity(line)
                                res = i + 1
                return res

        def read_and_discard_matching_from_argument(self, fmri_set):
                """Reads the file and removes all frmis in the file
                from fmri_set.
                """
                if self._file_handle:
                        for line in self._file_handle:
                                f = fmri.PkgFmri(line)
                                fmri_set.discard(f)

        def count_entries_removed_during_partial_indexing(self):
                """Returns the number of entries removed during a second phase
                of indexing."""
                return len(self._set)