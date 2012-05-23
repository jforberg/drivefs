#!/usr/bin/python2
# coding: utf-8 

import sys
import posixpath
import errno

from sys import argv
import time

from fuse import *

#import gdata.data
import gdata.docs.service
#import gdata.docs.data

__author__ = 'johan@forberg.se (Johan Förberg)'

APP_NAME = 'DriveFS'
DEBUG = False
CODING = 'utf-8'

def gdtime_to_ctime(timestr):
    # Note: milliseconds are stripped away.
    # Sample Google time: 2012-05-22T19:07:06.721Z
    timestr = timestr[0:timestr.find('.')] # Cut away decimals
    t = time.strptime(timestr, '%Y-%m-%dT%H:%M:%S')
    return time.mktime(t) # Convert to C-style time_t

def drive_connect(username, password):
    client = gdata.docs.service.DocsService(source=APP_NAME)
    client.http_client.debug = DEBUG
    client.ClientLogin(username, password)
    return client

def path_to_uri(path):
    if len(path) < 1 or path[0] != '/':
        raise FuseOSError(errno.ENOENT)
    if path =='/':
        return 'https://docs.google.com/feeds/documents/private/full'
    else:
        pl = posixpath.split(path)
        if len(pl) != 1:
            raise FuseOSError(errno.ENOENT)
        fn = pl[0][1:]
        q = gdata.docs.service.DocumentQuery()
        q['title'] = fn
        q['title-exact'] = 'true'
        return q.ToUri()

class DriveFS(Operations):
    """"""
    def __init__(self, username, password, path='/'):
        self.client = drive_connect(username, password)
        self.root = path

    def __del__(self):
        # Destroy drive connection
        pass

    def readdir(self, path, fh=None):
        feed = self.client.GetDocumentListFeed(path_to_uri(path))
        return ['.', '..'] + \
            [entry.title.text.decode(CODING) for entry in feed.entry]

    def getattr(self, path, fh=None):
        feed = client.Query(path_to_uri(path))
        if not feed.entry:
            raise FuseOSError(errno.ENOENT)
        elif len(feed.entry) != 1:
            raise Error('Non-unique filename!')
        f = feed.entry[0]
        st = {}
        st['st_mtime'] = f.updated.text

if __name__ == '__main__':
    if len(argv) != 4:
        print 'Usage: %s <username> <password> <mountpoint>' % argv[0]
        exit(1)
    fs = FUSE(DriveFS(argv[1], argv[2]), argv[3], 
              foreground=True, nothreads=True)

