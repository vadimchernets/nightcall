---
name: awake
description: Keep this computer from falling asleep for 8 or 12 hours (or any number the person picks) and let it sleep again by itself afterwards - Mac (caffeinate), Linux (systemd-inhibit) and Windows (SetThreadExecutionState) - no administrator rights. Also shows whether it is on and until when, and switches it off early. Use when the person says "keep it awake", "don't let it sleep tonight", "keep awake", "caffeinate" (in any language), or before any night run.
argument-hint: "<8 | 12 | hours | 30m | status | stop>"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(powershell *) Bash(pwsh *) Bash(date*)
---

# Nightcall: coffee for the computer

The person said: $ARGUMENTS

Answer in the person's language.

1. **How long.** A number in the request is hours (8, 12, 10) or minutes with `m` (`30m`). No number:
   ask once — "8 hours, or 12?" — and if there is no answer in two minutes, take 8.

2. **Switch it on** for this system:

   - Mac or Linux:
     ```
     bash "${CLAUDE_PLUGIN_ROOT}/scripts/awake.sh" <hours>
     ```
   - Windows (PowerShell is always there; bash usually is not):
     ```
     powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/scripts/awake-windows.ps1" -Hours <hours>
     ```
     (`-Minutes 30` for minutes. `-ExecutionPolicy Bypass` applies to this one run only.)

   `status` and `stop` work the same way (`-Status`, `-Stop` on Windows).

3. **Show the script's own lines** — "ON until 07:15" and the warnings under it. Do not
   paraphrase them into something more confident. If it says DID NOT TURN ON, say so.

4. **The three things the person sets by hand**, one line each, only the ones that apply:
   - the laptop lid: leave it open;
   - the charger: plug it in for the whole night;
   - system updates: pause them for tonight.

The coffee ends by itself at the end time. Forgetting to switch it off costs nothing.
