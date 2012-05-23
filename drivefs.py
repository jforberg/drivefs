#!/usr/bin/python2
# coding: utf-8 

import sys
from time import time

from fuse import FUSE, Operations, LoggingMixIn

#fuse.fuse_python_api = (0, 2)

#import gdata.data
import gdata.docs.service
#import gdata.docs.data

__author__ = 'johan@forberg.se (Johan Förberg)'

APP_NAME = 'DriveFS'
DEBUG = False

def drive_connect(username, password):
    client = gdata.docs.service.DocsService(source=APP_NAME)
    client.http_client.debug = DEBUG
    client.ClientLogin(username, password)
    return client

class DriveFS(Operations):
    """"""
    def __init__(self, username, password, path='/'):
        self.gdclient = drive_connect(username, password)
        self.root = path

    def __del__(self):
        # Destroy drive connection
        pass

    def readdir(self, path, fh):
        

if __name__ == '__main__':
    fs = FUSE(DriveFS(argv[1], argv[2]), foreground=True, nothreads=True)

