#!/bin/bash

LOG_FILE="/home/pi/snuphya/snuphya.log"

echo "$(date +'%Y-%m-%d %H:%M:%S') Starting snuphya" >> "$LOG_FILE"
python /home/pi/snuphya/main.py >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo "$(date +'%Y-%m-%d %H:%M:%S') [ERROR] snuphya script execution failed!" >> "$LOG_FILE"
fi