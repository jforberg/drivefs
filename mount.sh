#!/bin/sh

source ./config.sh

./drivefs.py "$username" "$password" "$mountpoint" &
echo $! > drivefs.$mountpoint.pid


