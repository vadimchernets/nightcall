#!/usr/bin/env bash
# Nightcall box: the whole night runs in a sandbox that sees only the task folder.
#
#   bash night-loop.sh --box "<task folder>" [hours]   # the night, boxed (night-loop.sh hands over here)
#   bash box.sh stop "<task folder>"                   # stop it right now, one command
#   bash box.sh key [claude|codex]                     # put the sign-in token into this Mac's Keychain once
#   bash box.sh plan "<task folder>" [hours]           # print what would run (mode, command, sandbox rules)
#   bash box.sh rules "<task folder>"                  # only the sandbox rules, as JSON
#
# What the box gives: files - only the task folder is writable, the rest of the home folder is not even
# readable (no ~/.ssh, ~/.aws, other projects); network - only the hosts in box/allow.txt (+ the folder's
# box-allow.txt, + NIGHTCALL_BOX_ALLOW); keys - none lie in the box: the subscription token comes from the
# host's Keychain (`claude setup-token` -> `bash box.sh key`) as an environment variable of this one run.
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
image=${NIGHTCALL_BOX_IMAGE:-nightcall-box:2}
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
pidfile="$state/$tag.pid"

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
  python3 - "$folder" "$root" "$here/box/allow.txt" "${NIGHTCALL_BOX_ALLOW:-}" "$([ -n "$codex_key" ] && echo key)" <<'PY'
import json, os, sys
folder, root, allow_file, extra, codex_key = sys.argv[1:6]
home = os.path.expanduser("~")
hosts = []
for path in (allow_file, os.path.join(folder, "box-allow.txt")):
    if os.path.isfile(path):
        hosts += [l.strip() for l in open(path, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
hosts += extra.split()
H = lambda p: os.path.join(home, p)
nightcall = os.environ.get("NIGHTCALL_HOME", H(".nightcall"))
# claude's own install (~/.local, npm prefix) and settings are readable; the rest of the home folder is not
read = [folder, root, H(".claude"), H(".claude.json"), H(".local"), H(".npm"), H(".config/claude"),
        H(".pocketcall"), nightcall, H(".codex")]
write = [folder, H(".claude"), H(".claude.json"), H(".claude.json.backup"), H(".codex"),
         H(".pocketcall/board"), nightcall, "/private/tmp", "/tmp", H(".npm")]
deny_write = [H(".claude/settings.json"), H(".claude/hooks"), H(".claude/plugins"), H(".claude/skills"),
              H(".codex/config.toml"), root]
deny_read = [home]
if codex_key:  # the Codex key comes from the Keychain, so the sign-in file stays out of reach
    deny_read.append(H(".codex/auth.json"))
print(json.dumps({
    "network": {"allowedDomains": sorted(set(hosts)), "deniedDomains": []},
    "filesystem": {"denyRead": deny_read, "allowRead": read, "allowWrite": write, "denyWrite": deny_write},
}, indent=1))
PY
}

loop_env=(NIGHTCALL_IN_BOX=1 "NIGHTCALL_FAMILY=${NIGHTCALL_FAMILY:-off}")

if [ "$mode" = docker ]; then
  run=(docker run --rm --name "$name" --init --cap-add NET_ADMIN --cap-add NET_RAW
       -v "$folder:$folder" -v "$root:/opt/nightcall:ro" -w "$folder"
       -e NIGHTCALL_IN_BOX=1 -e "NIGHTCALL_FAMILY=${NIGHTCALL_FAMILY:-off}" -e NIGHTCALL_BOARD=off
       -e "NIGHTCALL_BOX_ALLOW=${NIGHTCALL_BOX_ALLOW:-}"
       -e "TZ=${TZ:-$(readlink /etc/localtime 2>/dev/null | sed 's#.*zoneinfo/##')}")   # the night's clock = this computer's
  for v in NIGHTCALL_PERMISSION_MODE NIGHTCALL_MODEL NIGHTCALL_MAX_ROUNDS NIGHTCALL_LIMIT_WAIT; do
    [ -n "${!v:-}" ] && run+=(-e "$v")
  done
  [ -n "$claude_token" ] && run+=(-e CLAUDE_CODE_OAUTH_TOKEN)   # name only: the value travels in the env
  [ -n "${ANTHROPIC_API_KEY:-}" ] && run+=(-e ANTHROPIC_API_KEY)
  [ -n "$codex_key" ] && run+=(-e OPENAI_API_KEY)
  run+=("$image" -- bash /opt/nightcall/scripts/night-loop.sh "$folder" "$hours")
else
  mkdir -p "$state"
  settings="$state/$tag.srt.json"
  run=(npx -y -p "$srt_pkg" srt --settings "$settings" -- env "${loop_env[@]}" bash "$here/night-loop.sh" "$folder" "$hours")
fi

[ "$cmd" = rules ] && { srt_settings; exit 0; }   # just the sandbox rules (JSON), for checks
if [ "$cmd" = plan ]; then
  echo "mode: $mode"
  echo "folder: $folder (the only writable place besides Claude's and Codex's own state)"
  echo "sign-in: claude $([ -n "$claude_token" ] && echo "token from the Keychain" || echo "API key or none") / codex $([ -n "$codex_key" ] && echo "key from the Keychain" || echo "its own sign-in")"
  echo "stop: bash $here/box.sh stop \"$folder\""
  printf 'command:'; printf ' "%s"' "${run[@]}"; echo
  [ "$mode" = srt ] && { echo "rules:"; srt_settings; }
  [ "$mode" = docker ] && echo "image: $image from $here/box/Dockerfile; network: $here/box/allow.txt"
  exit 0
fi

echo "$(date '+%F %T') nightcall box ($mode): only $folder, network by box/allow.txt; stop: bash $here/box.sh stop \"$folder\"" | tee -a "$folder/night-loop.log"
[ -n "$claude_token" ] && export CLAUDE_CODE_OAUTH_TOKEN="$claude_token"
[ -n "$codex_key" ] && export OPENAI_API_KEY="$codex_key"
if [ "$mode" = docker ]; then
  docker image inspect "$image" >/dev/null 2>&1 || docker build -t "$image" "$here/box" || exit 4
  # keep this computer awake from the outside: the container has no caffeinate
  bash "$here/awake.sh" "$hours" >/dev/null 2>&1 || true
  exec "${run[@]}"
fi
srt_settings > "$settings"
bash "$here/awake.sh" "$hours" >/dev/null 2>&1 || true   # caffeinate from the outside: the sandbox closes it
echo $$ > "$pidfile"
"${run[@]}"
rc=$?
rm -f "$pidfile"
exit $rc
