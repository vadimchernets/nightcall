#!/usr/bin/env bash
# Nightcall — keep a Linux computer awake for the night, then let it sleep again by itself.
#
#   bash awake-linux.sh 8        # 8 hours (also: 12, any whole number of hours)
#   bash awake-linux.sh 90m      # minutes, for a short test
#   bash awake-linux.sh status
#   bash awake-linux.sh stop
#
# First choice: `systemd-inhibit` (ships with almost every modern distribution), which holds a
# lock against idle, sleep and — where the desktop allows it — the lid switch, for exactly as long
# as a `sleep N` runs. No administrator rights. When the time is up, the lock goes away by itself.
# Fallbacks, in order: gnome-session-inhibit, then a loop that nudges the screensaver with xdg/xset.
set -u

STATE_DIR="${NIGHTCALL_HOME:-$HOME/.nightcall}"
STATE="$STATE_DIR/awake-linux.pid"
UNTIL_FILE="$STATE_DIR/awake-linux.until"
HOW_FILE="$STATE_DIR/awake-linux.how"

say() { printf '%s\n' "$*"; }

running_pid() {
  [ -f "$STATE" ] || return 1
  pid=$(cat "$STATE" 2>/dev/null)
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && { printf '%s' "$pid"; return 0; }
  return 1
}

cmd_status() {
  if pid=$(running_pid); then
    say "ВКЛЮЧЕНО: компьютер не заснёт до $(cat "$UNTIL_FILE" 2>/dev/null) ($(cat "$HOW_FILE" 2>/dev/null), процесс $pid)."
    return 0
  fi
  say "ВЫКЛЮЧЕНО: компьютер засыпает как обычно."
  return 1
}

cmd_stop() {
  if pid=$(running_pid); then
    # kill the whole group: the inhibitor and the `sleep` it is holding
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null
    pkill -P "$pid" 2>/dev/null || true
    rm -f "$STATE" "$UNTIL_FILE" "$HOW_FILE"
    say "ВЫКЛЮЧЕНО: кофеин снят, компьютер снова засыпает как обычно."
  else
    rm -f "$STATE" "$UNTIL_FILE" "$HOW_FILE"
    say "Кофеин и так не был включён."
  fi
}

to_seconds() {
  case "$1" in
    *s) n=${1%s}; case "$n" in ''|*[!0-9]*) return 1;; esac; printf '%s' "$n";;   # seconds, for tests
    *m) n=${1%m}; case "$n" in ''|*[!0-9]*) return 1;; esac; printf '%s' $((n * 60));;
    *h) n=${1%h}; case "$n" in ''|*[!0-9]*) return 1;; esac; printf '%s' $((n * 3600));;
    *)  n=$1;     case "$n" in ''|*[!0-9]*) return 1;; esac; printf '%s' $((n * 3600));;
  esac
}

start_bg() {  # run "$@" detached in its own process group, print its pid
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "$@" >/dev/null 2>&1 &
  else
    nohup "$@" >/dev/null 2>&1 &
  fi
  printf '%s' "$!"
}

cmd_start() {
  secs=$(to_seconds "$1") || { say "Не понял срок «$1». Пример: 8, 12, 10h или 30m."; exit 2; }
  [ "$secs" -gt 0 ] || { say "Срок должен быть больше нуля."; exit 2; }
  if [ "$secs" -gt $((24 * 3600)) ]; then say "Больше 24 часов не ставлю — поставьте заново утром."; exit 2; fi
  mkdir -p "$STATE_DIR"
  if running_pid >/dev/null; then cmd_stop >/dev/null; fi

  why="Nightcall: агент работает ночью"
  pid=""; how=""
  if command -v systemd-inhibit >/dev/null 2>&1; then
    # with the lid first; some desktops refuse the lid lock, then without it
    for what in "idle:sleep:handle-lid-switch" "idle:sleep"; do
      pid=$(start_bg systemd-inhibit --what="$what" --who=nightcall --why="$why" --mode=block sleep "$secs")
      sleep 0.5
      if kill -0 "$pid" 2>/dev/null; then how="systemd-inhibit --what=$what"; break; fi
      pid=""
    done
  fi
  if [ -z "$pid" ] && command -v gnome-session-inhibit >/dev/null 2>&1; then
    pid=$(start_bg gnome-session-inhibit --inhibit idle:suspend --reason "$why" sleep "$secs")
    sleep 0.5
    if kill -0 "$pid" 2>/dev/null; then how="gnome-session-inhibit"; else pid=""; fi
  fi
  if [ -z "$pid" ]; then
    # Last resort: every 50 s (or less, near the end) tell the screensaver the user is here,
    # until the time is up. The step is capped to what's left so a short spell (a test run, or
    # the last stretch of a long one) ends on time instead of overshooting by up to 50 s.
    end=$(( $(date +%s) + secs ))
    pid=$(start_bg sh -c "while [ \$(date +%s) -lt $end ]; do
      xdg-screensaver reset 2>/dev/null || xset s reset 2>/dev/null
      left=\$(( $end - \$(date +%s) ))
      [ \"\$left\" -gt 50 ] && left=50
      [ \"\$left\" -gt 0 ] || break
      sleep \"\$left\"
    done")
    how="запасной путь: сброс заставки каждые 50 с (сон по таймеру он держит не везде)"
  fi

  printf '%s' "$pid" > "$STATE"
  printf '%s' "$how" > "$HOW_FILE"
  until_h=$(date -d "+${secs} seconds" '+%H:%M %d.%m' 2>/dev/null || date '+%H:%M')
  printf '%s' "$until_h" > "$UNTIL_FILE"
  say "ВКЛЮЧЕНО: компьютер не заснёт до $until_h ($((secs / 3600)) ч $(((secs % 3600) / 60)) мин), потом кофеин снимется сам."
  say "  чем: $how, процесс $pid"
  case "$how" in *handle-lid-switch*) say "  Крышку можно закрыть — lid-lock взят. Надёжнее всё же оставить открытой.";;
    *) say "  Крышку ноутбука НЕ закрывайте: закрытая крышка усыпит компьютер.";; esac
  on_ac=""
  for f in /sys/class/power_supply/*/online; do [ -f "$f" ] && [ "$(cat "$f")" = "1" ] && on_ac=1; done
  ls /sys/class/power_supply/BAT* >/dev/null 2>&1 || on_ac=1   # no battery = desktop
  if [ -n "$on_ac" ]; then say "  питание: от сети — хорошо."; else say "  ВНИМАНИЕ: сейчас от батареи — подключите зарядку."; fi
  say "  Снять раньше: bash \"$0\" stop"
}

case "${1:-}" in
  ""|-h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
  status) cmd_status;;
  stop) cmd_stop;;
  *) cmd_start "$1";;
esac
