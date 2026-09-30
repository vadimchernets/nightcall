#!/usr/bin/env bash
# Nightcall — keep a Mac awake for the night, then let it sleep again by itself.
#
#   bash awake-mac.sh 8          # 8 hours (also: 12, any whole number of hours)
#   bash awake-mac.sh 90m        # minutes, for a short test
#   bash awake-mac.sh status     # is it on, and until when
#   bash awake-mac.sh stop       # switch it off now
#   NIGHTCALL_SCREEN=off bash awake-mac.sh 8   # keep the computer awake, let the screen go dark
#
# Uses the `caffeinate` that ships with every Mac. No administrator rights, nothing installed.
# `caffeinate -t` ends on its own when the time is up, so forgetting to stop it costs nothing.
set -u

STATE_DIR="${NIGHTCALL_HOME:-$HOME/.nightcall}"
STATE="$STATE_DIR/awake-mac.pid"
UNTIL_FILE="$STATE_DIR/awake-mac.until"

say() { printf '%s\n' "$*"; }

running_pid() {
  [ -f "$STATE" ] || return 1
  pid=$(cat "$STATE" 2>/dev/null)
  [ -n "$pid" ] || return 1
  # The pid must still be OUR caffeinate, not some other program that got the number later.
  if ps -p "$pid" -o comm= 2>/dev/null | grep -q caffeinate; then
    printf '%s' "$pid"; return 0
  fi
  return 1
}

cmd_status() {
  if pid=$(running_pid); then
    say "ВКЛЮЧЕНО: Mac не заснёт до $(cat "$UNTIL_FILE" 2>/dev/null) (процесс caffeinate $pid)."
    return 0
  fi
  say "ВЫКЛЮЧЕНО: Mac засыпает как обычно."
  return 1
}

cmd_stop() {
  if pid=$(running_pid); then
    kill "$pid" 2>/dev/null
    sleep 0.3
    if ps -p "$pid" >/dev/null 2>&1; then kill -9 "$pid" 2>/dev/null; fi
    rm -f "$STATE" "$UNTIL_FILE"
    say "ВЫКЛЮЧЕНО: кофеин снят, Mac снова засыпает как обычно."
  else
    rm -f "$STATE" "$UNTIL_FILE"
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

cmd_start() {
  secs=$(to_seconds "$1") || { say "Не понял срок «$1». Пример: 8, 12, 10h или 30m."; exit 2; }
  [ "$secs" -gt 0 ] || { say "Срок должен быть больше нуля."; exit 2; }
  if [ "$secs" -gt $((24 * 3600)) ]; then say "Больше 24 часов не ставлю — поставьте заново утром."; exit 2; fi
  command -v caffeinate >/dev/null 2>&1 || { say "На этом компьютере нет caffeinate — это точно Mac?"; exit 3; }

  mkdir -p "$STATE_DIR"
  if running_pid >/dev/null; then cmd_stop >/dev/null; fi

  # -i no idle sleep · -m disk stays up · -s no system sleep on mains power · -u "user is here"
  # -d screen stays on: a browser behind a dark screen is slowed down, and the web chats need it.
  flags="-imsu"
  [ "${NIGHTCALL_SCREEN:-on}" = "off" ] || flags="-dimsu"

  nohup caffeinate "$flags" -t "$secs" >/dev/null 2>&1 &
  pid=$!
  disown "$pid" 2>/dev/null || true
  sleep 0.3
  if ! ps -p "$pid" >/dev/null 2>&1; then say "НЕ ВКЛЮЧИЛОСЬ: caffeinate сразу закрылся."; exit 4; fi
  printf '%s' "$pid" > "$STATE"
  until_h=$(date -v+"${secs}"S '+%H:%M %d.%m' 2>/dev/null || date '+%H:%M')
  printf '%s' "$until_h" > "$UNTIL_FILE"

  say "ВКЛЮЧЕНО: Mac не заснёт до $until_h ($((secs / 3600)) ч $(((secs % 3600) / 60)) мин), потом кофеин снимется сам."
  say "  процесс caffeinate $pid, флаги $flags"
  if pmset -g batt 2>/dev/null | head -1 | grep -q "AC Power"; then
    say "  питание: от сети — хорошо."
  else
    say "  ВНИМАНИЕ: сейчас от батареи — за ночь она может сесть, и тогда Mac уснёт. Подключите зарядку."
  fi
  say "  Крышку ноутбука НЕ закрывайте: закрытая крышка усыпляет Mac, кофеин этого не отменяет."
  say "  Снять раньше: bash \"$0\" stop"
}

case "${1:-}" in
  ""|-h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
  status) cmd_status;;
  stop) cmd_stop;;
  *) cmd_start "$1";;
esac
