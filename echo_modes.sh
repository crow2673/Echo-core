#!/bin/bash

while true; do
    echo ""
    echo "===== Echo Modes ====="
    echo "1) Workday Mode"
    echo "2) Focus Mode"
    echo "3) Low Power Mode"
    echo "4) High Performance Mode"
    echo "5) Exit"
    echo "======================"
    read -p "Choose a mode (1-5): " mode

    case $mode in
        1) ~/Echo/modes/workday_mode.sh ;;
        2) ~/Echo/modes/focus_mode.sh ;;
        3) ~/Echo/modes/low_power_mode.sh ;;
        4) ~/Echo/modes/high_perf_mode.sh ;;
        5) exit 0 ;;
        *) echo "Invalid choice." ;;
    esac
done
