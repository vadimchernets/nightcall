#!/usr/bin/env bash
# Nightcall — one entry for Mac and Linux: picks the right "coffee" for this computer.
#   bash awake.sh 8 | 12 | 10h | 30m | status | stop
# On Windows use awake-windows.ps1 (see the README): bash is usually not there.
here=$(cd "$(dirname "$0")" && pwd)
case "$(uname -s)" in
  Darwin) exec bash "$here/awake-mac.sh" "$@";;
  Linux)  exec bash "$here/awake-linux.sh" "$@";;
  MINGW*|MSYS*|CYGWIN*)
    h=${1:-}
    case "$h" in
      ""|-h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
      stop) exec powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$here/awake-windows.ps1" 2>/dev/null || echo "$here/awake-windows.ps1")" -Stop;;
      status) exec powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$here/awake-windows.ps1" 2>/dev/null || echo "$here/awake-windows.ps1")" -Status;;
      *m) exec powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$here/awake-windows.ps1" 2>/dev/null || echo "$here/awake-windows.ps1")" -Minutes "${h%m}";;
      *) exec powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$here/awake-windows.ps1" 2>/dev/null || echo "$here/awake-windows.ps1")" -Hours "${h%h}";;
    esac;;
  *) echo "Didn't recognize the system $(uname -s). Mac: awake-mac.sh, Linux: awake-linux.sh, Windows: awake-windows.ps1"; exit 3;;
esac
