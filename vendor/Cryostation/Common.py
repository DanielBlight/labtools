#!/usr/bin/env python3
import datetime

# This script contains functions used across Montana Instruments Cryostation python scripts.

def dtprint(msg):
    now = datetime.datetime.now()
    print("{0} {1}".format(now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], msg))
