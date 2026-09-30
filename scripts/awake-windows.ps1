# Nightcall - keep a Windows computer awake for the night, then let it sleep again by itself.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File awake-windows.ps1 -Hours 8
#   powershell -NoProfile -ExecutionPolicy Bypass -File awake-windows.ps1 -Hours 12
#   powershell -NoProfile -ExecutionPolicy Bypass -File awake-windows.ps1 -Minutes 2     # short test
#   powershell -NoProfile -ExecutionPolicy Bypass -File awake-windows.ps1 -Status
#   powershell -NoProfile -ExecutionPolicy Bypass -File awake-windows.ps1 -Stop
#   add -ScreenOff to let the screen go dark while the computer keeps working
#
# Uses the Windows function SetThreadExecutionState - the same one PowerToys Awake uses. It holds
# only while the process that called it is alive, so a small hidden PowerShell keeps running until
# the time is up and then exits: the lock goes away by itself. No administrator rights.
# "-ExecutionPolicy Bypass" applies to this one run only and changes no setting on the computer.
param(
  [int]$Hours = 0,
  [int]$Minutes = 0,
  [switch]$Stop,
  [switch]$Status,
  [switch]$ScreenOff
)

$ErrorActionPreference = 'Stop'
$dir = Join-Path $env:LOCALAPPDATA 'nightcall'
$pidFile = Join-Path $dir 'awake-windows.pid'
$untilFile = Join-Path $dir 'awake-windows.until'

function Get-Running {
  if (-not (Test-Path $pidFile)) { return $null }
  $p = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $p) { return $null }
  $proc = Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue
  if ($proc -and $proc.ProcessName -match 'powershell|pwsh') { return $proc }
  return $null
}

if ($Status) {
  $r = Get-Running
  if ($r) { Write-Output ("ВКЛЮЧЕНО: компьютер не заснёт до {0} (процесс {1})." -f (Get-Content $untilFile), $r.Id); exit 0 }
  Write-Output 'ВЫКЛЮЧЕНО: компьютер засыпает как обычно.'; exit 1
}

if ($Stop) {
  $r = Get-Running
  if ($r) { Stop-Process -Id $r.Id -Force; Write-Output 'ВЫКЛЮЧЕНО: кофеин снят, компьютер снова засыпает как обычно.' }
  else { Write-Output 'Кофеин и так не был включён.' }
  Remove-Item $pidFile, $untilFile -ErrorAction SilentlyContinue
  exit 0
}

$secs = $Hours * 3600 + $Minutes * 60
if ($secs -le 0) { Write-Output 'Укажите срок: -Hours 8, -Hours 12 или -Minutes 30.'; exit 2 }
if ($secs -gt 86400) { Write-Output 'Больше 24 часов не ставлю — поставьте заново утром.'; exit 2 }

New-Item -ItemType Directory -Force -Path $dir | Out-Null
$old = Get-Running
if ($old) { Stop-Process -Id $old.Id -Force }

# ES_CONTINUOUS 0x80000000 | ES_SYSTEM_REQUIRED 0x1 | ES_DISPLAY_REQUIRED 0x2
# written in decimal: a hex literal above 0x7FFFFFFF is a negative Int32 in PowerShell 5
$flags = if ($ScreenOff) { '2147483649' } else { '2147483651' }
$worker = @"
Add-Type -Namespace Nightcall -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
`$end = (Get-Date).AddSeconds($secs)
while ((Get-Date) -lt `$end) {
  [Nightcall.Power]::SetThreadExecutionState([uint32]$flags) | Out-Null
  Start-Sleep -Seconds 60
}
[Nightcall.Power]::SetThreadExecutionState([uint32]2147483648) | Out-Null
"@
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($worker))
$exe = (Get-Process -Id $PID).Path
$p = Start-Process -FilePath $exe -ArgumentList @('-NoProfile', '-WindowStyle', 'Hidden', '-EncodedCommand', $encoded) -WindowStyle Hidden -PassThru

Start-Sleep -Milliseconds 800
if ($p.HasExited) { Write-Output 'НЕ ВКЛЮЧИЛОСЬ: фоновый процесс сразу закрылся.'; exit 4 }
Set-Content -Path $pidFile -Value $p.Id
$until = (Get-Date).AddSeconds($secs).ToString('HH:mm dd.MM')
Set-Content -Path $untilFile -Value $until

Write-Output ("ВКЛЮЧЕНО: компьютер не заснёт до {0} ({1} ч {2} мин), потом кофеин снимется сам." -f $until, [math]::Floor($secs / 3600), [math]::Floor(($secs % 3600) / 60))
Write-Output ("  фоновый процесс {0}, флаги {1}" -f $p.Id, $(if ($ScreenOff) { "система (экран может гаснуть)" } else { "система + экран" }))
try {
  $bat = Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue
  if ($bat -and $bat.BatteryStatus -ne 2) { Write-Output '  ВНИМАНИЕ: сейчас от батареи — подключите зарядку.' }
  else { Write-Output '  питание: от сети — хорошо.' }
} catch { }
Write-Output '  Крышку ноутбука НЕ закрывайте (или в «Электропитание → Действие при закрытии крышки» выберите «Ничего не делать» для питания от сети).'
Write-Output '  Обновления Windows могут перезагрузить ночью: Параметры → Центр обновления → Приостановить на 1 неделю или «Период активности» на ночь.'
Write-Output ('  Снять раньше: powershell -NoProfile -ExecutionPolicy Bypass -File "{0}" -Stop' -f $PSCommandPath)
