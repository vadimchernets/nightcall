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
# Model: NIGHTCALL_MODEL (default: whatever Claude Code uses). On Windows run it from Git Bash or WSL; the plain Claude Code session (/nightcall:start) works anywhere.
set -u

folder=${1:?"Give the task folder: bash night-loop.sh <folder> [hours]"}
hours=${2:-8}
case "$hours" in ''|*[!0-9]*) echo "Hours must be a whole number, e.g. 8 or 12."; exit 2;; esac
[ -f "$folder/PLAN.md" ] || { echo "No PLAN.md in $folder — /nightcall:start writes the plan first."; exit 2; }
command -v claude >/dev/null 2>&1 || { echo "The claude command was not found."; exit 3; }

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

round=0
while :; do
  now=$(date +%s)
  [ "$now" -lt "$end" ] || { echo "$(date '+%F %T') time is up" | tee -a "$log"; break; }
  [ -f "$folder/MORNING.md" ] && { echo "$(date '+%F %T') MORNING.md is ready — the night is over" | tee -a "$log"; break; }
  [ -f "$folder/STOP" ] && { echo "$(date '+%F %T') STOP found — stopping" | tee -a "$log"; break; }
  [ "$round" -lt "$max_rounds" ] || { echo "$(date '+%F %T') hit the $max_rounds-round ceiling" | tee -a "$log"; break; }
  round=$((round + 1))
  echo "$(date '+%F %T') round $round" | tee -a "$log"
  out=$(cd "$folder" && claude -p "$prompt" --permission-mode "$mode" ${NIGHTCALL_MODEL:+--model "$NIGHTCALL_MODEL"} 2>&1)
  rc=$?
  printf '%s\n' "$out" | tail -20 >> "$log"
  if printf '%s' "$out" | grep -qiE "usage limit|limit reached|rate.?limit|hit your limit|resets? (at|in)"; then
    echo "$(date '+%F %T') subscription limit — waiting $((limit_wait / 60)) min and trying again" | tee -a "$log"
    round=$((round - 1))
    sleep "$limit_wait"
  elif [ "$rc" -ne 0 ]; then
    echo "$(date '+%F %T') the round ended with code $rc — next one in a minute" | tee -a "$log"
    sleep 60
  fi
done

if [ ! -f "$folder/MORNING.md" ]; then
  (cd "$folder" && claude -p "The night on the nightcall plugin is over. Folder: $folder. Write MORNING.md following skill nightcall:morning's template, in this order: \"Needs your decision\" (from decisions.md: the council's decisions with an undo command for each, and questions waiting for an answer; plus morning-advice.md, if it exists) / \"Done\" / \"Not done\" / \"Check\" / \"Who took part\" — strictly from PROGRESS.md and git log, making nothing up." --permission-mode "$mode" ${NIGHTCALL_MODEL:+--model "$NIGHTCALL_MODEL"} >> "$log" 2>&1)
fi
echo "$(date '+%F %T') loop finished. Report: $folder/MORNING.md" | tee -a "$log"
