#!/usr/bin/env bash
# Nightcall box: the whole night runs in a sandbox that sees only the task folder.
#
#   bash night-loop.sh --box "<task folder>" [hours]   # the night, boxed (night-loop.sh hands over here)
#   bash box.sh stop "<task folder>"                   # stop it right now, one command
#   bash box.sh key [claude|codex]                     # put the sign-in token into this Mac's Keychain once
#   bash box.sh plan "<task folder>" [hours]           # print what would run (mode, command, sandbox rules)
#   bash box.sh rules "<task folder>"                  # only the sandbox rules, as JSON
#
# What the box gives: files - the task folder is the only place of yours it reads and writes; the rest
# of the home folder (other projects, ~/.ssh, ~/.aws, your Claude Code and Codex history and settings)
# is not even readable. The box has its own homes for Claude Code, Codex, npm and the board
# (~/.nightcall/box/<id>/), so nothing it writes ever runs later outside it. Network - only the hosts in
# box/allow.txt (+ the folder's box-allow.txt, + NIGHTCALL_BOX_ALLOW). Keys - none lie in the box: the
# subscription token comes from the host's Keychain (`claude setup-token` -> `bash box.sh key`) as an
# environment variable of this one run. The board on the phone: the box writes only plain data into its
# own card; box/relay.py, outside, checks it field by field and puts the line on pocketcall's board with
# the night's folder, hours and box: true - never a command.
#
# Two kinds of box, picked by itself (NIGHTCALL_BOX=srt|docker to choose):
#   docker - when Docker answers (Docker Desktop, colima, OrbStack): a real container, the egress firewall
#            from Anthropic's reference dev container, non-root user. Image built once from box/Dockerfile.
#   srt    - otherwise: Anthropic's sandbox runtime (@anthropic-ai/sandbox-runtime) wraps the whole loop -
#            claude, codex, python, git - in macOS Seatbelt (Linux: bubblewrap). Nothing to install on a Mac:
#            npx fetches it on the first run.
# Docs (checked 2026-10-07): code.claude.com/docs/en/sandbox-environments, .../sandboxing, .../devcontainer.
set -u

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
state=${NIGHTCALL_HOME:-$HOME/.nightcall}/box
srt_pkg=${NIGHTCALL_SRT:-@anthropic-ai/sandbox-runtime@0.0.79}
image=${NIGHTCALL_BOX_IMAGE:-nightcall-box:3}
cmd=run
case "${1:-}" in stop|key|plan|rules) cmd=$1; shift;; esac

keychain() {  # keychain <account>: the token stored by `box.sh key`, empty when there is none
  command -v security >/dev/null 2>&1 || return 0
  security find-generic-password -s nightcall-box -a "$1" -w 2>/dev/null || true
}

if [ "$cmd" = key ]; then
  who=${1:-claude}
  if [ "$who" = claude ]; then
    echo "Claude Code prints a one-year token for your subscription; paste it at the prompt below."
    claude setup-token
  else
    echo "Paste the Codex / OpenAI key at the prompt below."
  fi
  security add-generic-password -U -s nightcall-box -a "$who" -w || exit 1
  echo "Saved in the Keychain as nightcall-box/$who. Every boxed night takes it from there."
  exit 0
fi

folder=${1:?"Give the task folder: bash night-loop.sh --box <folder> [hours]"}
hours=${2:-8}
[ -d "$folder" ] || { echo "No such folder: $folder"; exit 2; }
folder=$(cd "$folder" && pwd -P)
tag=$(printf '%s' "$folder" | shasum | cut -c1-10)
name="nightcall-box-$tag"
pidfile="$state/$tag.pid"          # outside the box's own home: the box cannot touch it
own="$state/$tag"                  # the box's own homes: claude, codex, npm, tmp, the board card

kill_tree() {  # the process and everything it started
  local p
  for p in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$p"; done
  kill -TERM "$1" 2>/dev/null || true
}

if [ "$cmd" = stop ]; then
  touch "$folder/STOP"
  stopped=""
  if command -v docker >/dev/null 2>&1 && docker rm -f "$name" >/dev/null 2>&1; then stopped="container $name"; fi
  if [ -f "$pidfile" ]; then kill_tree "$(cat "$pidfile")"; rm -f "$pidfile"; stopped="${stopped:+$stopped, }sandbox"; fi
  bash "$here/awake.sh" stop >/dev/null 2>&1 || true   # and the laptop may sleep again
  echo "Stopped: ${stopped:-nothing was running}; the STOP file keeps the next start from going on by itself (delete it to run again)."
  exit 0
fi

mode=${NIGHTCALL_BOX:-auto}
case "$mode" in srt|docker) ;; *) mode=auto;; esac   # NIGHTCALL_BOX=1 (the phone's Continue) = pick by itself
if [ "$mode" = auto ]; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then mode=docker; else mode=srt; fi
fi

# the sign-in for this run only: from the Keychain into the environment of the box, never into a file
claude_token=${CLAUDE_CODE_OAUTH_TOKEN:-$(keychain claude)}
codex_key=${OPENAI_API_KEY:-$(keychain codex)}
if [ -z "$claude_token" ] && [ -z "${ANTHROPIC_API_KEY:-}" ] && [ "$cmd" = run ] && [ -t 0 ]; then
  echo "First boxed night: the box takes your subscription from the Keychain - setting it up now (once)."
  bash "$0" key claude && claude_token=$(keychain claude)
fi
if [ -z "$claude_token" ] && [ -z "${ANTHROPIC_API_KEY:-}" ] && [ "$cmd" = run ]; then
  echo "The box signs in with a token from the Keychain - run once: bash $here/box.sh key   (then start the night again)"
  exit 3
fi

srt_settings() {  # the sandbox rules as JSON
  python3 - "$folder" "$root" "$own" "$here/box/allow.txt" "${NIGHTCALL_BOX_ALLOW:-}" <<'PY'
import json, os, shutil, sys
folder, root, own, allow_file, extra = sys.argv[1:6]
home = os.path.expanduser("~")
hosts = []
for path in (allow_file, os.path.join(folder, "box-allow.txt")):
    if os.path.isfile(path):
        hosts += [l.strip() for l in open(path, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
hosts += extra.split()
# the programs the night runs, when they live in the home folder: their install folders only (read)
tools = set()
for c in ("claude", "node", "npx", "npm", "codex", "gemini", "python3", "git"):
    p = shutil.which(c)
    if not p or not p.startswith(home + os.sep):
        continue
    tools.add(os.path.dirname(p))                       # the bin folder with the link
    real = os.path.realpath(p)
    if "/node_modules/" in real:
        head, tail = real.split("/node_modules/", 1)
        parts = tail.split("/")
        tools.add(os.path.join(head, "node_modules", *parts[:2 if parts[0].startswith("@") else 1]))
    else:
        tools.add(os.path.dirname(os.path.dirname(real)))   # .../node/bin/node -> .../node
tools = sorted(t for t in tools if t.startswith(home + os.sep) and t != home)
print(json.dumps({
    "network": {"allowedDomains": sorted(set(hosts)), "deniedDomains": []},
    "filesystem": {"denyRead": [home], "allowRead": [folder, root, own] + tools,
                   "allowWrite": [folder, own], "denyWrite": [root]},
}, indent=1))
PY
}

git_name=$(git config --global user.name 2>/dev/null || true)
git_mail=$(git config --global user.email 2>/dev/null || true)
# inside: its own homes; the board card is plain data in its own folder (relay.py carries it out)
inside=(NIGHTCALL_IN_BOX=1 NIGHTCALL_BOX= "NIGHTCALL_FAMILY=${NIGHTCALL_FAMILY:-off}" NIGHTCALL_BOARD=box-relay
        "GIT_AUTHOR_NAME=$git_name" "GIT_AUTHOR_EMAIL=$git_mail" "GIT_COMMITTER_NAME=$git_name" "GIT_COMMITTER_EMAIL=$git_mail")

if [ "$mode" = docker ]; then
  run=(docker run --rm --name "$name" --init --cap-add NET_ADMIN --cap-add NET_RAW
       -v "$folder:$folder" -v "$root:/opt/nightcall:ro" -v "$own/pocketcall:/home/node/.pocketcall" -w "$folder"
       -e POCKETCALL_HOME=/home/node/.pocketcall -e "NIGHTCALL_BOX_ALLOW=${NIGHTCALL_BOX_ALLOW:-}"
       -e "TZ=${TZ:-$(readlink /etc/localtime 2>/dev/null | sed 's#.*zoneinfo/##')}")   # the night's clock = this computer's
  for v in "${inside[@]}"; do run+=(-e "$v"); done
  for v in NIGHTCALL_PERMISSION_MODE NIGHTCALL_MODEL NIGHTCALL_MAX_ROUNDS NIGHTCALL_LIMIT_WAIT; do
    [ -n "${!v:-}" ] && run+=(-e "$v")
  done
  [ -n "$claude_token" ] && run+=(-e CLAUDE_CODE_OAUTH_TOKEN)   # name only: the value travels in the env
  [ -n "${ANTHROPIC_API_KEY:-}" ] && run+=(-e ANTHROPIC_API_KEY)
  [ -n "$codex_key" ] && run+=(-e OPENAI_API_KEY -e CODEX_API_KEY)
  run+=("$image" -- bash /opt/nightcall/scripts/night-loop.sh "$folder" "$hours")
else
  settings="$state/$tag.srt.json"   # outside the box's own home: the box cannot loosen its rules
  run=(env "npm_config_cache=$state/npx" npx -y -p "$srt_pkg" srt --settings "$settings" --
       env "${inside[@]}" "CLAUDE_CONFIG_DIR=$own/claude" "CODEX_HOME=$own/codex" "NIGHTCALL_HOME=$own/nightcall"
       "POCKETCALL_HOME=$own/pocketcall" "npm_config_cache=$own/npm" "TMPDIR=$own/tmp" "CLAUDE_CODE_TMPDIR=$own/tmp"
       "PATH=$own/bin:$PATH" bash "$here/night-loop.sh" "$folder" "$hours")
fi

if [ "$cmd" = rules ]; then srt_settings; exit 0; fi
if [ "$cmd" = plan ]; then
  echo "mode: $mode"
  echo "folder: $folder (the only place of yours the box reads and writes; its own homes: $own)"
  echo "sign-in: claude $([ -n "$claude_token" ] && echo "token from the Keychain" || echo "API key") / codex $([ -n "$codex_key" ] && echo "key from the Keychain" || echo "its own sign-in, copied for the night")"
  echo "stop: bash $here/box.sh stop \"$folder\""
  printf 'command:'; printf ' "%s"' "${run[@]}"; echo
  [ "$mode" = srt ] && { echo "rules:"; srt_settings; }
  [ "$mode" = docker ] && echo "image: $image from $here/box/Dockerfile; network: $here/box/allow.txt"
  exit 0
fi

echo "$(date '+%F %T') nightcall box ($mode): only $folder, network by box/allow.txt; stop: bash $here/box.sh stop \"$folder\"" | tee -a "$folder/night-loop.log"
mkdir -p "$state" "$own/claude" "$own/codex" "$own/nightcall" "$own/pocketcall/board" "$own/npm" "$own/tmp" "$own/bin"
chmod 700 "$state" "$own"
echo $$ > "$pidfile"
[ -n "$claude_token" ] && export CLAUDE_CODE_OAUTH_TOKEN="$claude_token"
[ -n "$codex_key" ] && export OPENAI_API_KEY="$codex_key" CODEX_API_KEY="$codex_key"
# Codex on a ChatGPT subscription: its sign-in file goes into the box's own Codex home for this night
# and is taken back out when the night ends
if [ -z "$codex_key" ] && [ -f "$HOME/.codex/auth.json" ]; then
  install -m 600 "$HOME/.codex/auth.json" "$own/codex/auth.json"
fi
# the box's claude loads the nightcall plugin from this copy (its own Claude home has no plugins)
if [ "$mode" = srt ] && real=$(command -v claude); then
  printf '#!/bin/sh\nexec "%s" --plugin-dir "%s" "$@"\n' "$real" "$root" > "$own/bin/claude"
  chmod 755 "$own/bin/claude"
fi
bash "$here/awake.sh" "$hours" >/dev/null 2>&1 || true   # caffeinate from the outside: the box closes it
python3 "$here/box/relay.py" --src "$own/pocketcall/board" --folder "$folder" --hours "$hours" --watch $$ \
  </dev/null >/dev/null 2>&1 &
if [ "$mode" = docker ]; then
  docker image inspect "$image" >/dev/null 2>&1 || docker build -t "$image" "$here/box" || exit 4
  "${run[@]}"
else
  srt_settings > "$settings"
  "${run[@]}"
fi
rc=$?
rm -f "$pidfile" "$own/codex/auth.json"
exit $rc
