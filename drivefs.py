#!/usr/bin/python2
# coding: utf-8 

import sys
import posixpath
import errno
import os
import time
import re
import stat

from sys import argv

from fuse import *

#import gdata.data
import gdata.docs.service
#import gdata.docs.data

__author__ = 'johan@forberg.se (Johan Förberg)'

APP_NAME   = 'DriveFS'
MY_DEBUG   = True
FUSE_DEBUG = False
CODING     = 'utf-8'

class DriveFSError(Exception):
    pass

def gdtime_to_ctime(timestr):
    # Note: milliseconds are stripped away.
    # Sample Google time: 2012-05-22T19:07:06.721Z
    timestr = timestr[0:timestr.find('.')] # Cut away decimals
    t = time.strptime(timestr, '%Y-%m-%dT%H:%M:%S')
    return int(time.mktime(t)) # Convert to C-style time_t

def drive_connect(username, password):
    client = gdata.docs.service.DocsService(source=APP_NAME)
    client.http_client.debug = FUSE_DEBUG
    client.ClientLogin(username, password)
    return client

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

def get_filesize(self):
    # Hacking a filesize getter onto the Drive API
    # NOTE: A shameless kludge.
    s = self.ToString()
    try:
        m = re.search(r'<ns.:quotaBytesUsed.*>(\d+)</ns.:quotaBytesUsed>', s)
        filesize = int(m.groups()[0])
        return filesize
    except AttributeError: # No match
        return 0 # Couldn't determine file size

gdata.docs.DocumentListEntry.get_filesize = get_filesize

class DriveFS(Operations):
    """"""
    def __init__(self, email, password, path='/'):
        self.client = drive_connect(email, password)
        self.root = path
        self.my_uid = os.getuid()
        self.my_gid = os.getgid()
        self.email = email

    def __del__(self):
        # Destroy drive connection
        pass

    def readdir(self, path, fh=None):
        if MY_DEBUG:
            print 'readdir(%s)' % path
        feed = self.client.GetDocumentListFeed(path_to_uri(path))
        return ['.', '..'] + \
            [entry.title.text.decode(CODING) for entry in feed.entry]
    def getattr(self, path, fh=None):
        """Build and return a stat(2)-like dict of attributes."""
        if MY_DEBUG:
            print 'getattr(%s)' % path
        # Default values
        DEFMODE = (stat.S_IFREG | stat.S_IRUSR | stat.S_IRGRP |
                   stat.S_IROTH )
        st = {'st_ctime': 0, 'st_mtime': 0, 'st_atime': 0,
              'st_uid': self.my_uid, 'st_gid': self.my_gid,
              'st_mode': DEFMODE, 'st_nlink': 1, 'st_size': 0}
        if path == '/':
            st['st_mode'] &= ~stat.S_IFREG # Is not regular
            st['st_mode'] |=  stat.S_IFDIR # Is directory
            return st
        else:
            feed = self.client.Query(path_to_uri(path))
            if not feed.entry:
                raise FuseOSError(errno.ENOENT)
            elif len(feed.entry) != 1:
                raise Exception('Non-unique filename!')
            f = feed.entry[0]
            st['st_ctime'] = gdtime_to_ctime(f.published.text \
                                             if f.published  else 0)
            st['st_mtime'] = gdtime_to_ctime(f.updated.text \
                                             if f.updated    else 0)
            st['st_atime'] = gdtime_to_ctime(f.lastViewed.text \
                                             if f.lastViewed else 0)
            st['st_size']  = f.get_filesize()
            return st

if __name__ == '__main__':
    if len(argv) != 4:
        print 'Usage: %s <username> <password> <mountpoint>' % argv[0]
        exit(1)
    fs = FUSE(DriveFS(argv[1], argv[2]), argv[3], 
              foreground=True, nothreads=True)

