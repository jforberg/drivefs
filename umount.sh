#!/bin/sh

source ./config.sh

kill `cat drivefs.$mountpoint.pid` && rm drivefs.$mountpoint.pid

#fusermount -u "$mountpoint"
