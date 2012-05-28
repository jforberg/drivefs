#!/usr/bin/python2
# coding: utf-8 
#
# Copyright (c) 2012, Johan Förberg <johan@forberg.se>.  All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.  
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.  
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import sys
import posixpath
import errno
import os
import time
import re
import stat
import tempfile
import httplib
import urlparse

from sys import argv

from fuse import *

import gdata.service as gdata
import gdata.docs.service as gdocs # API relevant to Drive

__author__ = 'Johan Förberg <johan@forberg.se>'

KBYTES  = 2**10
MBYTES  = 2**20

APP_NAME   = 'DriveFS'
MY_DEBUG   = True
FUSE_DEBUG = False
CODING     = 'utf-8'
#CHUNKSIZE  = 4 * MBYTES # Size of a cache chunk.

class GDBaseFile:
    def __init__(self, entry=None):
        # entry == None means I am the root dir.
        name  = entry.title.text if entry else '/'
        self.name = name.decode(CODING)
        self.stat = {
            'st_ctime': 0,
            'st_mtime': 0,
            'st_atime': 0,
            'st_uid':   os.getuid(),
            'st_gid':   os.getgid(),
            'st_mode':  (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH),
            'st_nlink': 1,
            'st_size':  0,
            # The blocksize affects the default buffer size for file reads
            'st_blksize': 65536
        }
        # The id is a unique identifier which can be used to fetch the object
        # from Google
        self.uri = entry.id.text if entry \
                else gdocs.DocumentQuery().ToUri() # Root element.

    # Magic filesize getter.
    size = property(lambda self: self.stat['st_size'])

    def __repr__(self):
        return '<%s %s at 0x%x>' % (self.__class__.__name__, 
                                    self.name, id(self))

class GDDir(GDBaseFile):
    def __init__(self, entry=None, dirs=[], files=[]):
        GDBaseFile.__init__(self, entry)
        self.stat['st_mode'] |= (stat.S_IFDIR |
                                 stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.files = files
        self.dirs  = dirs

    def child(self, name):
        for d in self.dirs:
            if d.name == name:
                return d
        for f in self.files:
            if f.name == name:
                return f
        # No child was found
        raise KeyError('Does not exist: %s/%s' % (self.name, name))
        return None

class GDFile(GDBaseFile):
    def __init__(self, entry, client):
        GDBaseFile.__init__(self, entry)
        self.stat['st_ctime'] = gdtime_to_ctime(
                entry.published.text  if entry.published  else 0)
        self.stat['st_mtime'] = gdtime_to_ctime(
                entry.updated.text  if entry.updated  else 0)
        self.stat['st_atime'] = gdtime_to_ctime(
                entry.lastViewed.text  if entry.lastViewed  else 0)
        self.stat['st_mode'] |= stat.S_IFREG
        self.stat['st_size']  = get_filesize(entry)
        self.uri = entry.id.text
        self.src = entry.content.src
        self.cache = None
        self.is_open = False
        self.client = client

    def open(self):
        if not self.is_open:
            self.is_open = True

    def close(self):
        if self.is_open:
            self.cache = None # Clear the cache
            self.is_open = False

    def read(self, size=None, offset=0):
        if not self.is_open:
            raise DriveFSError('%s is not open for reading!' % self.name)
        if size is None:
            size = self.size - offset
        if not self.cache:
            data = None
            # It is not an error to request data beyond the end of the file.
            if self.size == 0 or offset > self.size:
                return ''
            if offset + size > self.size:
                size = self.size - offset
            # The request fails unless Range is present, for unknown reasons.
            headers = {'Range': 'bytes=%d-%d' % (offset, offset + size)}
            try: 
                data = self.client.Get(self.src, extra_headers=headers)
                # Google API will raise an exception even if the request
                # succeeds with status 206 (Partial Content), as intended.
            except gdata.RequestError as err:
                if err[0]['status'] == httplib.PARTIAL_CONTENT:
                    data = err[0]['body'] # The data we were looking for.
                else: 
                    data = None
                    raise # There was some other error.
            self.cache = data

        # We now have a cached copy of the file.
        return self.cache[offset:size + offset]

class DriveFSError(Exception):
    pass

class DriveFS(Operations):
    def __init__(self, email, password, path='/'):
        self.email = email
        self.root = None
        self.cache = (None, None)

        self.client = gdocs.DocsService(source=APP_NAME)
        self.client.http_client.debug = FUSE_DEBUG
        self.client.ClientLogin(email, password)

        self.refresh_tree() # Set self.root

    def __del__(self):
        # Destroy drive connection
        pass

    def __repr__(self):
        return '<%s for %s at 0x%x>' % (self.__class__.__name__, self.email, 
                                        id(self))

    def getfile(self, path):
        pl = full_split(path)
        if not pl or pl.pop() != '/': # Removes /
            raise DriveFSError('Path was not absolute: %s' % path)
        f = self.root 
        try:
            while pl:
                f = f.child(pl.pop())
        except KeyError:
            raise FuseOSError(errno.ENOENT)
        else:
            return f

    def refresh_tree(self):
        q = gdocs.DocumentQuery(params={'showfolders': 'false'})
        entries = self.client.GetDocumentListFeed(q.ToUri()).entry
        # Construct root tree.
        self.root = GDDir(None, files=[GDFile(e, self.client) for e in entries])

    ###
    ### FUSE method overloads
    ###

    # These methods should be kept very simple.

    def readdir(self, path, fh):
        if MY_DEBUG:
            print 'readdir(%s, %s)' % (path.encode(CODING), fh)
        r = self.getfile(path)
        return ['.', '..'] + [f.name for f in r.dirs + r.files]

    def getattr(self, path, fh):
        """Build and return a stat(2)-like dict of attributes."""
        if MY_DEBUG:
            print 'getattr(%s, %s)' % (path.encode(CODING), fh)
        f = self.getfile(path)
        return f.stat

    def read(self, path, size, offset, fh):
        if MY_DEBUG:
            print 'read(%s, %s, %s, %s)' % \
                        (path.encode(CODING), size, offset, fh)
        f = self.getfile(path)
        return f.read(size, offset)

    def open(self, path, flags):
        f = self.getfile(path)
        f.open()
        return 0

    def release(self, path, fh):
        f = self.getfile(path)
        f.close()
        return 0

def gdtime_to_ctime(timestr):
    # Note: milliseconds are stripped away.
    # Sample Google time: 2012-05-22T19:07:06.721Z
    try:
        timestr = timestr[0:timestr.find('.')] # Cut away decimals
        t = time.strptime(timestr, '%Y-%m-%dT%H:%M:%S')
    except AttributeError: 
        return 0 # Dunno why this happens. Well, well.
    else:
        return int(time.mktime(t)) # Convert to C-style time_t

def drive_connect(username, password):
    return client

def full_split(head):
    """Split a path fully into components and return a reversed list."""
    l = []
    while True:
        (head, tail) = posixpath.split(head)
        if tail and head:
            l.append(tail)
            continue
        elif head: # Happens for absolute paths
            l.append(head)
            break
        elif tail: # Happens for non-absolute paths
            l.append(tail)
            break
        else:      # Should not happen.
            break
    return l # Will be reversed!

def path_to_uri(path):
    if len(path) < 1 or path[0] != '/':
        raise DriveFSError('Invalid path: %s' % path)
    if path =='/':
        return '/feeds/documents/private/full'
    else:
        pl = posixpath.split(path)
        if len(pl) != 2:
            raise DriveFSError('Invalid path: %s' % path)
        fn = pl[1]
        q = gdata.docs.service.DocumentQuery()
        q['title'] = fn.encode(CODING)
        q['title-exact'] = 'true'
        return q.ToUri()

def get_filesize(entry):
    # Hacking a filesize getter onto the Drive API
    # NOTE: A shameless kludge.
    s = entry.ToString()
    try:
        m = re.search(r':quotaBytesUsed.*>(\d+)</', s)
        filesize = int(m.groups()[0])
        return filesize
    except AttributeError: # No match
        return 0 # Couldn't determine file size

if __name__ == '__main__':
    if len(argv) != 4:
        print 'Usage: %s <username> <password> <mountpoint>' % argv[0]
        exit(1)
    fs = FUSE(DriveFS(argv[1], argv[2]), argv[3], 
              foreground=True, nothreads=True, ro=True)

