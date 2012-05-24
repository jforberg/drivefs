#!/usr/bin/python2
# coding: utf-8 

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

import gdata.docs.service as gdocs

__author__ = 'Johan Förberg <johan@forberg.se>'

APP_NAME   = 'DriveFS'
MY_DEBUG   = True
FUSE_DEBUG = False
CODING     = 'utf-8'

class GDDir:
    def __init__(self, entry=None, dirs=[], files=[]):
        # entry == None means I am the root dir.
        name  = entry.title.text if entry else '/'
        self.name = name.decode(CODING)
        self.files = files
        self.dirs  = dirs
        self.stat = {
            'st_ctime': 0,
            'st_mtime': 0,
            'st_atime': 0,
            'st_uid':   os.getuid(),
            'st_gid':   os.getgid(),
            'st_mode':  (stat.S_IFDIR | 
                         stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH |
                         stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH),
            'st_nlink': 1,
            'st_size':  get_filesize(entry) if entry else 0
        }
        # The id is a unique identifier which can be used to fetch the object
        # from Google
        self.uri = entry.id.text if entry \
                else gdocs.DocumentQuery().ToUri() # Root element.

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

    def __repr__(self):
        return '<%s %s at 0x%x>' % (self.__class__.__name__, 
                                    self.name, id(self))

class GDFile:
    def __init__(self, entry):
        self.name  = entry.title.text.decode(CODING)
        self.stat = {
            'st_ctime': gdtime_to_ctime(
                            entry.published.text  if entry.published  else 0),
            'st_mtime': gdtime_to_ctime(
                            entry.updated.text    if entry.updated    else 0),
            'st_atime': gdtime_to_ctime(
                            entry.lastViewed.text if entry.lastViewed else 0),
            'st_uid':   os.getuid(),
            'st_gid':   os.getgid(),
            'st_mode':  (stat.S_IFREG | stat.S_IRUSR | stat.S_IRGRP |
                         stat.S_IROTH ),
            'st_nlink': 1,
            'st_size':  get_filesize(entry)
        }
        self.uri = entry.id.text
        # Dunno why but the gd parameter makes the request fail.
        self.src = entry.content.src.replace('&gd=true', '')

    def __repr__(self):
        return '<%s %s at 0x%x>' % (self.__class__.__name__, 
                                    self.name, id(self))

class DriveFSError(Exception):
    pass

class DriveFS(Operations):
    """"""
    def __init__(self, email, password, path='/'):
        self.client = drive_connect(email, password)
        self.email = email
        self.root = None
        self.cache = {}

        self.refresh() # Set self.root

    def __del__(self):
        # Destroy drive connection
        pass

    def gdopen(self, path):
        pl = full_split(path)
        if not pl or pl.pop() != '/': # Removes /
            raise DriveFSError('Path was not absolute: %s' % path)
            return None
        f = self.root 
        try:
            while pl:
                f = f.child(pl.pop())
        except KeyError:
            raise FuseOSError(errno.ENOENT)
            return None
        else:
            return f

    def refresh(self):
#        q = gdocs.DocumentQuery(params={'showfolders': 'true'})
        q = gdocs.DocumentQuery(params={'showfolders': 'false'})
        entries = self.client.GetDocumentListFeed(q.ToUri()).entry
#        folders = [e for e in entries if 
#                        'folder' in [c.label for c in e.category]
#                  ]
#        d_dirs = []
#        for folder in folders:
#            children = [e for e in entries if
#                            folder.title.text in [c.label for c in e.category]
#                       ]
      
        # Construct root tree.
        self.root = GDDir(None, files=[GDFile(e) for e in entries])

    ###
    ### FUSE methods
    ###

    def readdir(self, path, fh):
        if MY_DEBUG:
            print 'readdir(%s, %s)' % (path.encode(CODING), fh)
        r = self.gdopen(path)
        return ['.', '..'] + [f.name for f in r.dirs + r.files]

    def getattr(self, path, fh):
        """Build and return a stat(2)-like dict of attributes."""
        if MY_DEBUG:
            print 'getattr(%s, %s)' % (path.encode(CODING), fh)
        f = self.gdopen(path)
        return f.stat

    def read(self, path, size, offset, fh):
        if MY_DEBUG:
            print 'read(%s, %s, %s, %s)' % \
                        (path.encode(CODING), size, offset, fh)
        f = self.gdopen(path)
        (scheme, host, path, params, query, fragment) \
                = urlparse.urlparse(f.src)
        resource = path + params + query + fragment
        con = httplib.HTTPSConnection(host)
        con.request('GET', resource, headers={'User-Agent': APP_NAME, 
                'Range': 'bytes=%d-%d' % (offset, size - offset)})
        response = con.getresponse()
        return response.read()

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
    client = gdocs.DocsService(source=APP_NAME)
    client.http_client.debug = FUSE_DEBUG
    client.ClientLogin(username, password)
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
              foreground=True, nothreads=True)

