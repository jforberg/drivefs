DriveFS
=======

Mount your Google Drive account as a FUSE filesystem.

Limitations in the protocol
-----------

  * Directories cannot really be nested, although a single file may belong to several folders.
    Directories are more properly thought of as categories.
  * Filename collisions are permitted by the protocol. This is unacceptable in a Unix filesystem, 
    so some name mangling will have to occur.
  * Files in Google's proprietary format ("docs") cannot be read. This limitation exist even in Google's
    offical client.

Limitations in my implementation
------------

  * The file system is read-only.
  * Directories not implemented yet.
  * File reads are currently very slow.
 
Dependencies
------------

  * [fusepy](http://code.google.com/p/fusepy/) (included in the current package)
  * [Google data API](http://code.google.com/p/gdata-python-client)
  * FUSE libraries version 2.6 or later
  * 2.5 <= Python < 3.0
