#!/usr/bin/env bash
# Nightcall night loop — the sturdiest way through a night: a fresh Claude Code for every step.
#
#   bash night-loop.sh "<task folder>" [hours]        # default 8
#
# Why a loop outside Claude: one long session can die — the window closes, the subscription
# limit runs out at 3 a.m., the context fills up. Here every round is a new `claude -p` that reads
# PLAN.md and PROGRESS.md in the task folder, does ONE step, writes it down and exits. The files
# carry the night, not the session (Anthropic, "Effective harnesses for long-running agents";
# the Ralph loop). If the limit runs out, the loop waits and tries again until it is back.
#
# Stops by itself when: the time is up · MORNING.md appears · a file named STOP appears in the
# task folder · max rounds (NIGHTCALL_MAX_ROUNDS, default 60) is reached.
# Permission mode: NIGHTCALL_PERMISSION_MODE (default "auto" — Claude Code decides what is safe
# without asking; "acceptEdits" is stricter; "bypassPermissions" asks nothing at all).
# Family relay: with ~/.nightcall/family.json (scripts/family.py, skill nightcall:family) a spent limit
# does not mean waiting - the next round runs in the next family member's own sign-in folder
# (CLAUDE_CONFIG_DIR / CODEX_HOME), and the change of hands is written into PROGRESS.md. NIGHTCALL_FAMILY=off
# runs the night on this computer's usual sign-in only.
# My subscriptions: with ~/.nightcall/mine.json (scripts/mine.py on, skill nightcall:mine) and no family, one
# person's own Claude -> Codex -> Gemini CLI carry the night in turn: a spent (or nearly spent, by the
# remaining-% sensor) Claude hands the next step to Codex, and the work comes back to Claude when it is back.
# NIGHTCALL_MINE=off runs Claude only.
# The board: with pocketcall the night is one line on its board (working / resting on a limit until HH:MM /
# done), the phone sees it next to every other job and rings when the night rests or ends (night.py board;
# NIGHTCALL_BOARD=off leaves the board alone).
# Model: NIGHTCALL_MODEL (default: whatever Claude Code uses). On Windows run it from Git Bash or WSL; the plain Claude Code session (/nightcall:start) works anywhere.
set -u
[ "${1:-}" = --box ] && { shift; exec bash "$(dirname "$0")/box.sh" "$@"; }   # --box: the night in a sandbox that sees only the task folder (box.sh)

folder=${1:?"Give the task folder: bash night-loop.sh <folder> [hours]"}
hours=${2:-8}
case "$hours" in ''|*[!0-9]*) echo "Hours must be a whole number, e.g. 8 or 12."; exit 2;; esac
[ -f "$folder/PLAN.md" ] || { echo "No PLAN.md in $folder — /nightcall:start writes the plan first."; exit 2; }
if ! command -v claude >/dev/null 2>&1; then
  # a family whose members work in Codex runs without claude; anyone else needs it
  # (or "my subscriptions" with Codex / Gemini CLI) runs without claude; anyone else needs it
  engines=""; [ "${NIGHTCALL_FAMILY:-on}" = off ] || engines=$(python3 "$(dirname "$0")/family.py" engines 2>/dev/null)
  [ "${NIGHTCALL_MINE:-on}" = off ] || engines="$engines $(python3 "$(dirname "$0")/mine.py" engines 2>/dev/null)"
  case " $engines " in
    *" codex "*|*" gemini "*) command -v codex >/dev/null 2>&1 || command -v gemini >/dev/null 2>&1 || { echo "The claude command was not found."; exit 3; };;
    *) echo "The claude command was not found."; exit 3;;
  esac
fi

here=$(cd "$(dirname "$0")" && pwd)
folder=$(cd "$folder" && pwd)
mode=${NIGHTCALL_PERMISSION_MODE:-auto}
max_rounds=${NIGHTCALL_MAX_ROUNDS:-60}
limit_wait=${NIGHTCALL_LIMIT_WAIT:-900}
end=$(( $(date +%s) + hours * 3600 ))
log="$folder/night-loop.log"

# the safety net, always: a restore point and the fence — if /nightcall:start has not made them yet
if ! grep -q 'nightcall:fence' "$folder/CLAUDE.md" 2>/dev/null; then
  python3 "$here/night.py" begin --dir "$folder" --hours "$hours" </dev/null | tee -a "$log"
fi
# web chats: the person's choice at the roll call — "night" (default, a reserve) or "morning".
# Read through team.py's own load_seats()/web_when(): a seats.json written before the English
# rename (Russian keys) must give the same answer as a current one, not silently fall back to the
# default because the raw key name changed.
web=$(python3 -c 'import sys
sys.path.insert(0, sys.argv[1])
try:
    import team as T
    print(T.web_when(T.load_seats(sys.argv[2])))
except Exception:
    print("night")' "$here" "$folder/seats.json")
if [ "$web" = morning ]; then
  web_rule="The person left web chats for the morning (web: morning): do NOT open them at night; if programs and keys do not answer, team.py ask will save the question into morning-advice.md by itself — then Claude's own critics (a fresh sub-agent)."
else
  web_rule="If programs and keys do not answer, and team.py ask's \"next\" is a web chat that passed the roll call — ask it there following skill nightcall:team §3 (one site at a time, no passwords); none available — Claude's own critics."
fi

# decisions that are normally the person's: "council" (default) or "morning" — the same file,
# through team.py's load_seats()/decide_when() for the same legacy-seats.json reason as $web above.
decide=$(python3 -c 'import sys
sys.path.insert(0, sys.argv[1])
try:
    import team as T
    print(T.decide_when(T.load_seats(sys.argv[2])))
except Exception:
    print("council")' "$here" "$folder/seats.json")
never="Never decide sending, publishing, paying, deleting without recovery, or signing in with a password — that is always a question for the morning (team.py hold)."
if [ "$decide" = morning ]; then
  decide_rule="A fork in the road that the person usually decides: do NOT decide it (the person chose \"all to the morning\"): python3 \"$here/team.py\" hold --dir \"$folder\" --question \"<question>\" --waits \"<what is on hold>\" --alt \"<options>\", mark the step \"waiting for an answer\" and take the next step or another part. $never"
else
  decide_rule="A fork in the road that the person usually decides: decide it with the AI council (team.py ask — other companies, then its own critics), without stopping: make it a SEPARATE commit and write it down: python3 \"$here/team.py\" decide --dir \"$folder\" --what \"<what was decided>\" --why \"<why>\" --who \"<who advised>\" --alt \"<other options>\" --commit <hash>. $never"
fi

mine=0
if [ "${NIGHTCALL_FAMILY:-on}" != off ] && python3 "$here/family.py" status >/dev/null 2>&1; then :
elif [ "${NIGHTCALL_MINE:-on}" != off ] && python3 "$here/mine.py" status --quiet >/dev/null 2>&1; then mine=1; fi
# the board line: the task folder and the command that goes on with the night (the phone's "Continue"),
# and in "my subscriptions" how much each one has left
board() {
  local m=""
  [ "$mine" = 1 ] && m=$(python3 "$here/mine.py" meter 2>/dev/null)
  # the card holds data, not a command: pocketcall's Continue rebuilds the loop's argv itself (no shell)
  python3 "$here/night.py" board --dir "$folder" --kind night --hours "$hours" --end "$end" \
    ${NIGHTCALL_BOX:+--box} ${m:+--meter "$m"} "$@" </dev/null >/dev/null 2>&1 || true
}

bash "$here/awake.sh" "$hours" | tee -a "$log"
echo "$(date '+%F %T') night loop: until $(date -r "$end" '+%H:%M' 2>/dev/null || date -d "@$end" '+%H:%M'), mode $mode, web chats: $web, forks in the road: $decide" | tee -a "$log"

prompt="You are working at night on the nightcall plugin, the person is asleep — don't ask them anything.
Task folder: $folder
1. Read TASK.md, PLAN.md, PROGRESS.md (and seats.json, if it exists).
2. Take the FIRST undone step from PLAN.md. Do it fully, check it against its \"done\" criterion.
3. Self-criticism: re-read the result through the eyes of a strict reviewer; if the step matters, ask
   a live helper: python3 \"$here/team.py\" ask --seats \"$folder/seats.json\" --dir \"$folder\" - (question on stdin).
   $web_rule
   Fix what you found, once.
   $decide_rule
4. Add to PROGRESS.md: time (date), step, what was done, how it was checked, what's left, disputed
   decisions under \"Check in the morning\". If the folder is under git — one commit per step.
5. If every step is done — write MORNING.md following skill nightcall:morning.
Do ONE step and end the turn."

family=0
if [ "${NIGHTCALL_FAMILY:-on}" != off ] && python3 "$here/family.py" status >/dev/null 2>&1; then
  family=1
  echo "$(date '+%F %T') family relay on: when one subscription rests, the next member's own account carries the work on" | tee -a "$log"
fi
who=""; engine=claude; cfg=""; name=""
if [ "$mine" = 1 ]; then
  echo "$(date '+%F %T') my subscriptions: $(python3 "$here/mine.py" engines | sed 's/ / -> /g'); the work moves on when one rests and comes back to the first" | tee -a "$log"
  engine=""
fi

# one round in the current hands: claude (or codex) in the member's own sign-in folder. In the family
# a round carries no key or token from this environment - only the member's own sign-in - and its
# Claude Code settings keep it out of the family's own places (family.py settings).
keys_out="-u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN -u OPENAI_API_KEY -u CODEX_API_KEY"
step() {
  local strip="" settings=""
  if [ "$family" = 1 ]; then
    strip=$keys_out
    settings=$(python3 "$here/family.py" settings --id "$who" 2>/dev/null)
  fi
  if [ "$engine" = gemini ]; then
    # --sandbox: Gemini CLI's own sandbox (Seatbelt on a Mac), as Codex runs in its workspace-write sandbox
    (cd "$folder" && env $strip gemini -p "$1" --yolo --sandbox 2>&1)
  elif [ "$engine" = codex ]; then
    (cd "$folder" && env $strip ${cfg:+"CODEX_HOME=$cfg"} codex exec -s workspace-write "$1" 2>&1)   # -s: current codex-cli (0.155 dropped --full-auto)
  else
    (cd "$folder" && env $strip ${cfg:+"CLAUDE_CONFIG_DIR=$cfg"} claude -p "$1" --permission-mode "$mode" ${settings:+--settings "$settings"} ${NIGHTCALL_MODEL:+--model "$NIGHTCALL_MODEL"} 2>&1)
  fi
}
# a limit is a failed round that says so, or a short answer that is only that (as team.py classify)
is_limit() {
  printf '%s' "$out" | grep -qiE "usage limit|limit reached|rate.?limit|hit your limit|resets? (at|in)|quota|RESOURCE_EXHAUSTED|\b429\b" || return 1
  [ "$rc" -ne 0 ] || [ "${#out}" -lt 300 ]
}

board --state working --note "until $(date -r "$end" '+%H:%M' 2>/dev/null || date -d "@$end" '+%H:%M')"
why=""
# killed, Ctrl-C or the terminal closed: the board says so instead of "working" forever
trap 'board --state failed --note "the loop was stopped (${why:-a signal}) - see $log"; exit 130' INT TERM HUP
round=0
while :; do
  now=$(date +%s)
  [ "$now" -lt "$end" ] || { why="time is up"; echo "$(date '+%F %T') $why" | tee -a "$log"; break; }
  [ -f "$folder/MORNING.md" ] && { why="MORNING.md is ready"; echo "$(date '+%F %T') MORNING.md is ready — the night is over" | tee -a "$log"; break; }
  [ -f "$folder/STOP" ] && { why="stopped by the STOP file"; echo "$(date '+%F %T') STOP found — stopping" | tee -a "$log"; break; }
  [ "$round" -lt "$max_rounds" ] || { why="$max_rounds rounds done"; echo "$(date '+%F %T') hit the $max_rounds-round ceiling" | tee -a "$log"; break; }
  if [ "$family" = 1 ]; then
    pick=$(python3 "$here/family.py" pick --folder "$folder" --after "$who" 2>>"$log")
    if [ -z "$pick" ]; then
      wait=$(python3 "$here/family.py" soonest 2>/dev/null || echo 0)
      case "$wait" in ''|*[!0-9]*) wait=0;; esac
      [ "$wait" -gt 0 ] && [ "$wait" -lt "$limit_wait" ] || wait=$limit_wait
      echo "$(date '+%F %T') every family subscription is resting - next try in $((wait / 60)) min" | tee -a "$log"
      board --state limit --rest "$wait" --note "every family subscription is resting"
      sleep "$wait"
      continue
    fi
    IFS="$(printf '\t')" read -r mid engine cfg name <<EOF_PICK
$pick
EOF_PICK
    [ "$cfg" = - ] && cfg=""
    if [ -n "$who" ] && [ "$mid" != "$who" ]; then
      python3 "$here/family.py" relay --folder "$folder" --from "$who" --to "$mid" | tee -a "$log"
    fi
    who=$mid
  fi
  if [ "$mine" = 1 ]; then
    pick=$(python3 "$here/mine.py" pick --after "$engine" 2>>"$log")
    if [ -z "$pick" ]; then
      wait=$(python3 "$here/mine.py" soonest 2>/dev/null || echo 0)
      case "$wait" in ''|*[!0-9]*) wait=0;; esac
      [ "$wait" -gt 0 ] && [ "$wait" -lt "$limit_wait" ] || wait=$limit_wait
      echo "$(date '+%F %T') every subscription of mine is resting - next try in $((wait / 60)) min" | tee -a "$log"
      board --state limit --rest "$wait" --note "every subscription of mine is resting"
      sleep "$wait"
      continue
    fi
    prev=${engine:-$(python3 "$here/mine.py" engines | awk '{print $1}')}   # the first night round: from the first in order
    if [ "$pick" != "$prev" ]; then
      line=$(python3 "$here/mine.py" relay --folder "$folder" --from "$prev" --to "$pick")
      echo "$line" | tee -a "$log"
      board --state working --say --note "$(python3 "$here/mine.py" say switched --to "$pick")"
    fi
    engine=$pick; name="mine"
  fi
  round=$((round + 1))
  echo "$(date '+%F %T') round $round${name:+ ($name, $engine)}" | tee -a "$log"
  board --state working --note "round $round${name:+ ($name, $engine)}"
  out=$(step "$prompt")
  rc=$?
  printf '%s\n' "$out" | tail -20 >> "$log"
  if [ "$family" = 1 ] && is_limit; then
    printf '%s' "$out" | python3 "$here/family.py" limit --id "$who" | tee -a "$log"
    round=$((round - 1))
    sleep 5
  elif [ "$mine" = 1 ] && is_limit; then
    printf '%s' "$out" | python3 "$here/mine.py" limit --engine "$engine" | tee -a "$log"
    round=$((round - 1))
    sleep 5
  elif printf '%s' "$out" | grep -qiE "usage limit|limit reached|rate.?limit|hit your limit|resets? (at|in)|quota|RESOURCE_EXHAUSTED|\b429\b"; then
    echo "$(date '+%F %T') subscription limit — waiting $((limit_wait / 60)) min and trying again" | tee -a "$log"
    if [ "$rc" -ne 0 ] || [ "${#out}" -lt 300 ]; then   # a real limit line, not work that mentions limits
      board --state limit --rest "$limit_wait" --note "the subscription rests; the night goes on by itself"
    fi
    round=$((round - 1))
    sleep "$limit_wait"
  elif [ "$rc" -ne 0 ]; then
    echo "$(date '+%F %T') the round ended with code $rc — next one in a minute" | tee -a "$log"
    sleep 60
  fi
done

if [ ! -f "$folder/MORNING.md" ]; then
  step "The night on the nightcall plugin is over. Folder: $folder. Write MORNING.md following skill nightcall:morning's template, in this order: \"Needs your decision\" (from decisions.md: the council's decisions with an undo command for each, and questions waiting for an answer; plus morning-advice.md, if it exists) / \"Done\" / \"Not done\" / \"Check\" / \"Who took part\" — strictly from PROGRESS.md and git log, making nothing up. Add a \"Relay\" line to \"Who took part\" if PROGRESS.md has a Relay section." >> "$log" 2>&1
fi
trap - INT TERM HUP
if [ -f "$folder/MORNING.md" ]; then
  board --state done --note "${why:+$why - }the report: $folder/MORNING.md"
else
  board --state failed --note "${why:-the loop ended} - no MORNING.md, see $log"
fi
echo "$(date '+%F %T') loop finished. Report: $folder/MORNING.md" | tee -a "$log"
