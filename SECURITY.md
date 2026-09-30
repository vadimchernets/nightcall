# Security

## What Nightcall touches

- **Keep-awake scripts** start one ordinary process (`caffeinate` on a Mac, `systemd-inhibit` on
  Linux, a hidden PowerShell calling `SetThreadExecutionState` on Windows) that ends by itself at the
  chosen time. No administrator rights, no system setting changed. State lives in `~/.nightcall/`
  (Windows: `%LOCALAPPDATA%\nightcall\`).
- **Helper AIs** are programs already installed and signed in by the person. They are called
  read-only (no writing, no commands), with environment variables that look like keys or tokens
  removed, so a paid API key that happens to be set is never used in place of the subscription.
- **The Stop hook** only acts while `~/.nightcall/active.json` exists, only for the session that
  started the night, and never past the end time, a `MORNING.md`, a `STOP` file or its round ceiling.
- **The night loop** starts `claude -p` in the task folder with the permission mode the person chose
  (`NIGHTCALL_PERMISSION_MODE`, default `auto`).

## What it never does

- Never asks for, stores or writes a password, key or card number.
- Never installs, signs in or buys anything; never uses a paid API.
- Never sends anything to other people unless that was the task.

## Reporting

Open an issue, or write to the author through the Poly A1 support address.
