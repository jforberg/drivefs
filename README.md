DriveFS
=======

Mount your Google Drive account as a FUSE filesystem.

Limitations
-----------

  * Read-only.
  * Flat filesystem hierarchy (directories to be implemented).
  * File reads are currently very slow.
 
Dependencies
------------

  * [fusepy](http://code.google.com/p/fusepy/)
  * fuse libraries version 2.6 or later
  * python 2.5 or later
