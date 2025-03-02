#!/usr/bin/env bash

# KEYBOARD_ID=$(xinput list | grep -i "slave  keyboard" | head -n1 | sed -n 's/.*id=\([0-9]*\).*/\1/p')
# echo "KEYBOARD_ID: $KEYBOARD_ID"
# # while xinput test $KEYBOARD_ID | grep -m1 --line-buffered "release.*\(133\|134\)" ; do
# #     sleep 0.1
# #     echo "waiting for Super_L to be pressed"
# # done
# while xinput query-state $KEYBOARD_ID | grep -q "key\[133\|134\]=down"; do  # 133 is typically Super_L
#     sleep 0.1
#     echo "waiting for Super_L to be released"
# done
#
# echo executing

sleep 1 # wait for the Win key to be released
qdbus org.srst.ClipboardMonitor /ClipboardMonitor explain
