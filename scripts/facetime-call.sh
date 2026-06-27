#!/bin/bash
# FaceTime video call shortcut — calls jaylee1217@gmail.com
# Usage: ./scripts/facetime-call.sh

set -euo pipefail

CONTACT="jaylee1217@gmail.com"

osascript <<EOF
tell application "FaceTime"
    activate
    open location "facetime://${CONTACT}"
end tell
delay 3
tell application "System Events"
    tell process "FaceTime"
        set frontmost to true
        delay 1
        set allElements to entire contents
        repeat with el in allElements
            try
                if role of el is "AXButton" and description of el is "通话" then
                    click el
                    exit repeat
                end if
            end try
        end repeat
    end tell
end tell
EOF
