---
name: ready
description: The checklist before leaving the computer working for the night - power, sleep and the laptop lid, system updates that restart at night, network, disk space, Claude Code permissions that would stop the night on the first question, the subscription limit, live helper AIs, and git for undo. Checked on the machine where it can be, named plainly where it cannot. Use before a night run, or when the person asks "что нужно, чтобы ночью всё работало", "проверь перед ночью", "ready for overnight".
argument-hint: "[task folder]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

# Nightcall: ready for the night?

The person said: $ARGUMENTS

Answer in the person's language.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ready.py" --dir "<task folder, if there is one>"
```

(`python3` missing on Windows: try `py -3`, then `python`.)

Show the result as three groups, short:

- **НЕ — исправить сейчас.** Each with its one action. Help the person do it right now, one at a
  time, and run the check again after. These are the reasons a night silently does nothing.
- **СЛЕДИТЕ — посмотрите своими глазами.** Things the script cannot read from here (the lid, the
  permission mode of this window, the Claude limit). One line each.
- **ОК** — one line in total: «Остальное в порядке: питание, сеть, место…».

The one to stress every time: **permissions**. Ask the person to switch this window to a mode that
does not stop to ask (Shift+Tab until auto or accept edits) and prove it with one real step while
they are still here. A night that stopped at 23:05 on «Разрешить?» looks in the morning exactly like
a night that did nothing.

If the person wants the phone to see the night's progress, and the Poly A1 plugin `pocketcall` is
installed, offer its `leave` skill after this list.
