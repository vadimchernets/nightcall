# Changelog

## 0.5.0 — 2026-10-07

- My subscriptions (`scripts/mine.py`, skill `/nightcall:mine`): one person's own Claude -> Codex -> Gemini CLI carry
  the night in turn. `night-loop.sh` picks the first program in the order that is installed, not resting and not
  nearly spent; a limit message rests that program until its reset time, the next one takes the next round from the
  same files, and the work returns to the first as soon as it is back. Every change of hands is a "Relay" line in
  PROGRESS.md. Gemini rounds run as `gemini -p ... --yolo`.
- The remaining-% sensor (from diffcall's core-poly/capacity): `mine.py capture` as Claude Code's `statusLine` command
  keeps the `rate_limits` numbers (five-hour / weekly, used %, reset time; nothing else of the payload); Codex is read
  live through `codex app-server` -> `account/rateLimits/read`. A fresh reading below `--below` (default 10%) hands the
  work over before a limit cuts a step in the middle; a stale one is not used.
- The week's reserve (`mine.py on --reserve`, default 20%): when a subscription's weekly window falls to the reserve,
  it rests until its week resets and the night goes on in the next one, so one night does not burn the week; the
  board's meter says "Claude keeps 20% of the week, back <day time>". `--reserve 0` spends the week to the end.
- After the cold critic: the Codex reading keeps the app-server's stdin open until the answer (closing it at once got
  no answer from the real server); a week's reading holds until the week's own reset (it only shrinks), so the reserve
  works in a headless night; Gemini rounds run with `--sandbox`, and its quota words (`quota`, `RESOURCE_EXHAUSTED`,
  `429`) count as a limit; the phone's lines ("switched to Codex - the work goes on", the meter) speak the phone's
  language (`lang/*.json` "phone"; NIGHTCALL_LANG, else pocketcall's); Codex rounds run `codex exec -s
  workspace-write` (codex-cli 0.155 refuses `--full-auto`); the board card is data - `--kind night --hours
  --end [--box]` - never a command; `mine.py capture --then "<your status line>"` keeps the person's own status line.
- The board: each night line carries the task folder, the command that goes on with the night (the phone's Continue
  button in pocketcall 0.5.0) and, in "my subscriptions", the meter (`--meter`); a change of hands rings at once
  (`--say`). With pocketcall before 0.5.0 the line goes without these fields. Tests: `tests/test_mine.py`.

## 0.4.1 — 2026-10-07

- The night on pocketcall's board: `night.py board` and `night-loop.sh` put each night on pocketcall 0.4.0's board
  as one line - working with the round and the hands it is in, resting on a limit until HH:MM (a spent limit, or
  every family subscription resting), done with the path of MORNING.md, or stopped with the reason. Pocketcall's
  `board.py put` rings the phone on the change (Telegram or the person's own ntfy topic) and rewrites the board's
  phone page; without pocketcall the line waits in `~/.pocketcall/board/`. `NIGHTCALL_BOARD=off` leaves the board
  alone, `NIGHTCALL_BOARD=<path>` names pocketcall's script. A night rings whether or not pocketcall says the person is
  away; a loop killed or closed says "stopped" on the board; two folders of the same name are two lines. Tests:
  `tests/test_board.py`.

## 0.4.0 — 2026-10-07

- Family relay (`scripts/family.py`, skill `/nightcall:family`), the family profiles of PolyHelper V1 brought to the
  night loop. Each member is added with their own e-mail and their own sign-in folder (`CLAUDE_CONFIG_DIR`, or
  `CODEX_HOME` with `--engine codex`), signs in there once with the vendor's own login, and gives a standing consent
  until a time they choose. In `night-loop.sh` a spent limit no longer means a 15-minute wait: the reset time is
  noted for that account, the next member whose folder is signed in as their named account takes the next round,
  and PROGRESS.md gets a "Relay" line. Everyone resting: the loop waits for the first account to come back. The family
  wording is V1's (`family-handoff.mjs` DISCLOSURE), word for word. Without `family.json`, or with
  `NIGHTCALL_FAMILY=off`, the loop is the same as in 0.3.10. Tests: `tests/test_family.py` (fake `claude`, including a
  full weekend loop run that hands over from Dad to Son).
- Family rounds run on the member's own sign-in only: `night-loop.sh` starts them with `env -u ANTHROPIC_API_KEY -u
  ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN -u OPENAI_API_KEY -u CODEX_API_KEY` and with Claude Code
  `--settings` from `family.py settings` (deny Read/Edit of `~/.nightcall/family/**`, the family list and log, the other
  members' sign-in folders). Consent is typed by the member in their own terminal (`/dev/tty`), only once their folder
  is signed in as them, after TASK.md and PLAN.md are on screen; the record is signed with the member's key in
  `~/.nightcall/family/<id>/consent.key`, and an unsigned or edited record counts as no consent. Family folders 0700,
  files 0600. A long answer that only mentions a rate limit no longer counts as a limit; with no claude and no Codex
  member the loop exits with code 3, as before.

## 0.3.10 — 2026-10-03

- Wording: no disclaimers. Every message the person or the model reads says what nightcall does, without excuses or
  apologies: the step-0 line is "nightcall is paused: it starts working the moment this computer has Python 3"; with no
  helper of another company alive, the roll call says "tonight's second head is Claude's own critics" and offers one fix;
  the keep-awake scripts and `/nightcall:ready` say "keep the laptop lid open" instead of what caffeine "does not
  override"; the README's closing note on web services' terms is gone. New `tests/test_no_disclaimers.py` scans every
  user- and model-facing text for stop phrases ("for now", "honestly", "unfortunately", "not legal advice", "own risk",
  and their Russian and Ukrainian forms) so they do not come back.

## 0.3.9 — 2026-10-02

- On Windows the step-0 launcher (`hooks/python.ps1`, and `hooks/python.sh` in Git Bash) also finds a Python installed
  after Claude Code started, with no restart: Claude Code hands its hooks and shells the PATH it was started with, so
  python.org's fresh Python is not on it. After `python`, `py -3` and `python3` on that PATH the launcher now looks at the
  `py` launcher (`%LOCALAPPDATA%\Programs\Python\Launcher`, `%SystemRoot%`), `%LOCALAPPDATA%\Programs\Python\Python3*`
  (and `%ProgramFiles%\Python3*`), newest first, and the install paths in the registry
  (`HKCU`/`HKLM\Software\Python\PythonCore\*\InstallPath`). Same proof as before: a candidate counts only once `-c`
  says 3.8+, and the Microsoft Store stub is never started. The step-0 line no longer asks for a restart. Checked on
  GitHub Actions windows-latest: Python installed silently in the middle of a job, then a hook (PowerShell 7 and 5.1),
  a skill's script and Git Bash ran on it with the PATH unchanged.

## 0.3.8 — 2026-10-02

- Skills run their scripts through the step-0 launcher, on every system: the Bash tool runs
  `sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/<name>.py ...`, the PowerShell tool (Windows without
  Git Bash) the same line starting with the bare path `${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1`. No skill calls `python3`
  any more (on Windows it is often missing or the Microsoft Store stub). The launcher takes a Python only once `-c`
  proves 3.8+, tries `python`, `py -3`, `python3` on Windows, never starts the Store or Apple stub, and with no Python
  says one step-0 line. Scripts are passed relative to the plugin root; text piped in PowerShell reaches the script as
  UTF-8 with no BOM (Windows PowerShell 5.1 wrote one). `allowed-tools` grant both forms, quoted as the command is -
  the old unquoted `Bash(python3 ${CLAUDE_PLUGIN_ROOT}/...)` never matched the quoted commands and always prompted.
  Checked on GitHub Actions on windows-latest, macos-latest and ubuntu-latest, including a real `claude -p` that opens a
  skill and runs its command with no prompt, through Bash and through PowerShell.

## 0.3.7 — 2026-10-02

- Hooks on Windows without Git Bash. There Claude Code runs hook commands in PowerShell, where `sh` does not
  exist, so the hooks failed. Each command in `hooks/hooks.json` is now two lines: sh and Git Bash run the first
  (`exec sh hooks/python.sh ...`, which never comes back); PowerShell finds no `exec`, goes on to the second (whose
  hoisted `trap { continue }` keeps it quiet about that) and
  loads `hooks/python.ps1` - the same step 0 guard (a real Python 3.8+ or one line and exit 0), as a script block
  so no execution policy stops it, with UTF-8 both ways. Checked on GitHub Actions on windows-latest (PowerShell 7,
  Windows PowerShell 5.1, Git Bash; with Python and without), macos-latest and ubuntu-latest, by a real
  `claude -p` session and by every hook command run the way Claude Code spawns it.
- `hooks/python.sh` exports `PYTHONUTF8=1`, so on Windows a hook reads non-English file names right.
- README: install from Poly A1's catalogue by its raw link (`/plugin marketplace add https://raw.githubusercontent.com/vadimchernets/poly-a1-plugins/main/.claude-plugin/marketplace.json`,
  then `/plugin install nightcall@poly-a1`) - no git needed; the Poly A1 folder is the way without internet,
  and `marketplace remove` is never the way to switch.

## 0.3.6 — 2026-10-02

- Step 0 guard: every hook now runs through `hooks/python.sh`, which starts the hook only with a
  real Python 3.8+. On a Mac without Command Line Tools it never runs the `/usr/bin/python3` stub (the
  one that pops Apple's install window mid-lesson); on Windows it skips the Microsoft Store stub and
  finds python.org's `python` or `py`. With no Python the session start says so in one line and the
  session goes on; nothing errors. Tests: `tests/test_step0.py`.
- Every release now carries `nightcall-0.3.6.zip` (one top folder `nightcall-0.3.6/`), built by the new
  `scripts/release-zip.sh` and attached by `.github/workflows/release.yml` on each `v*` tag. The Poly A1
  catalogue installs it as an `archive` source with its `sha256`, so installing needs no git: a
  beginner's Linux has none, and on a Mac without Apple's Command Line Tools `git` is the stub that
  opens Apple's install window.

## 0.3.5 — 2026-10-02

- Per-language word tables (quota / sign-in / reset-time recognition of helper messages) moved out of
  `scripts/team.py` into one data file per language: `lang/en.json`, `lang/ru.json` - loaded at import
  time from `lang/*.json`, same recognition behaviour as before.
- Added `lang/es.json`, `lang/pt.json`, `lang/uk.json`: the same recognition tables in Spanish,
  Portuguese (Brazilian-neutral) and Ukrainian, so a helper answering in one of those languages is
  recognised too.
- The legacy Russian field/status-name migration and the pre-0.3.4 Russian-named runtime files
  (`decisions.md`'s old name, `morning-advice.md`'s old name, `.who-is-who.json`'s old name, the old
  blind-answer file prefix) moved into `lang/ru.json`'s own `"legacy"` section - read-only, same
  behaviour; `scripts/team.py` now holds no Russian text at all, only the loader.
- Added `scripts/check_language.py` (run as part of `pytest`, via `tests/test_check_language.py`):
  fails if Cyrillic appears anywhere outside a language place (a `ru`/`uk` path part, a `*.ru.*`
  file name, or `lang/ru.json` / `lang/uk.json`). The project passes it clean.

## 0.3.4 — 2026-10-02

- Project language is English: comments, skill instructions, script output, PLAN/PROGRESS/MORNING templates
  and the Stop hook's text translated; skills report to the person in the person's language.
- Runtime names are English (`seats.json` keys and status words, `decisions.md`, `morning-advice.md`,
  `.who-is-who.json`, `answer-N.json`). Files written by 0.3.3 and earlier under the Russian names are still
  read (and an existing pre-0.3.4 Russian-named file, see `lang/ru.json` legacy, keeps being appended to);
  nothing on disk is renamed.
- Quota / sign-in / reset-time detection keeps recognising Russian messages from helpers, now as the `ru`
  entry of a per-language word table. `night-loop.sh` reads the web/decide choice through the same
  migration as `team.py`, so an old `seats.json` keeps its "morning" choice.

## 0.3.3 — 2026-10-02

- **Blind comparison** (owner, 01–02.10.2026): when Claude weighs the council, the answers are "Answer A /
  B / C", no company or model names — an AI judge leans to the answer that sounds like itself.
  `team.py ask --blind DIR` saves the answer without printing who gave it, `team.py blind --dir DIR`
  shows them shuffled as A / B / C, `team.py reveal --dir DIR` names them — only after the decision.
  README "Decisions…", `/nightcall:start` (council) and `/nightcall:team` say so. Test: names hidden
  until `reveal`.
- **429 on a free key → the next provider, not the next key or model of the same account.** Checked in
  the providers' docs 02.10.2026: the free limit is per project (Google AI Studio), per organization
  (Groq), per account (OpenRouter: «Making additional accounts or API keys will not affect your rate
  limits»; NVIDIA). A daily limit pauses it until the end of the run — only that model at Google and Groq
  (their quota is per model too), the whole of OpenRouter (`free-models-per-day` covers every :free
  model); a per-minute limit (all NVIDIA 429s) → the next provider now, this one once more at the end of
  the line, back in `seats.json` a minute later. The roll call still tries every model.

## 0.3.2 — 2026-10-01

- Free keys (the course lesson "Free AI keys") brought up to date, as in Poly A1 `src/duoAuto.ts`
  (checked live 01.10.2026): **NVIDIA first** (`NVIDIA_API_KEY`, Kimi K3 → GLM-5.3, 30 s per model in the
  roll call), then Google AI Studio (gemini-3.8 / 3.6 / 2.5-flash), Groq (Qwen 3.8, gpt-oss-120b — Llama
  is no longer free), OpenRouter :free (Qwen 3.8, Nemotron 3 Super, `openrouter/free` — no free DeepSeek
  there any more).
- Several models per key: 429/503/404/timeout → the next model of the same key; a key that is not
  accepted (401/403) is out at once; an empty answer → the next model too. The roll call shows which
  model answered. Request and answer as in duoAuto.ts: `max_tokens` 4096 on NVIDIA (Kimi K3 answered
  empty without it), 1500 on Groq, `<think>` and model service tokens (`<|close|>message`) cut out.
- Live roll call 01.10.2026: NVIDIA key — alive (Kimi K3, 1 s); Gemini AI Studio — alive (gemini-3.6-flash,
  3.8-flash gave way).
- Lesson references by name ("Free AI keys"), not "free-keys evenings".

## 0.3.1 — 2026-10-01

- The fence without the old step number 13A — by the lesson name "Fence and time machine".
