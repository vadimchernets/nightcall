# Step 0 guard, PowerShell twin of hooks/python.sh: run a hook script with a REAL Python 3, or do
# nothing at all.
#
#   <plugin> <say|quiet> <script.py> [args...]
#
# Why (02.10.2026). On Windows without Git Bash, Claude Code runs a hook command in PowerShell
# (`pwsh` or `powershell` -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command <command>),
# where `sh` does not exist. Every command in hooks.json is therefore two lines: the first,
# `exec sh .../python.sh ...`, is what sh and Git Bash run (exec replaces the shell, so they never
# read the second line); in PowerShell `exec` is no command, so it goes on to the second line, which
# loads this file as a script block - a script block is never stopped by the execution policy.
#
# Same rules as python.sh. python.org's Python is called `python` or `py` on Windows; `python` and
# `python3` may be the Microsoft Store stub, which answers `-c` with exit 9009 and never opens the
# Store, so a candidate counts only after `-c` proves it is Python 3.8+. Nothing found: `say` prints
# one line for Claude, `quiet` prints nothing; both exit 0. Stdin is left alone for the real script.
# The text both ways is UTF-8: Windows PowerShell would otherwise re-encode the script's output in
# the console's code page, and Python would read the hook's JSON in the ANSI one.
$plugin = $args[0]
$mode = $args[1]
$script = $args[2]
$rest = @($args | Select-Object -Skip 3)

$utf8 = New-Object System.Text.UTF8Encoding $false
try { [Console]::OutputEncoding = $utf8 } catch {}
$OutputEncoding = $utf8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$check = 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'
foreach ($candidate in @('python', 'py -3', 'python3')) {
  $words = $candidate.Split(' ')
  $exe = Get-Command $words[0] -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $exe) { continue }
  $pre = @($words | Select-Object -Skip 1)
  try { & $exe.Source @pre -c $check 2>$null | Out-Null } catch { continue }
  if ($LASTEXITCODE -ne 0) { continue }
  & $exe.Source @pre $script @rest
  exit $LASTEXITCODE
}

if ($mode -eq 'say') {
  Write-Output "$plugin is paused: this computer has no working Python 3 yet, so $plugin does nothing for now. Tell the person in one line and do step 0 first (in the Poly A1 folder it is the first step of START-HERE): Mac - xcode-select --install, then press Install in Apple's window and wait 5-10 minutes; Windows - winget install -e --id Python.Python.3.12 --scope user; Linux - sudo apt-get install -y python3. Then restart Claude Code."
}
exit 0
