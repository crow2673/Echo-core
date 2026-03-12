#!/bin/bash
DEVICE_ID="831262d329174260be1dd655ec255268"

# Force a refresh
kdeconnect-cli --refresh > /dev/null 2>&1

# Just try to send the ping; if it fails, it fails.
kdeconnect-cli -d $DEVICE_ID --ping-msg "$1" || echo "Failed to reach phone."
