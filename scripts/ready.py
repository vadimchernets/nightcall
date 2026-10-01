#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall ready: what has to be true for the night to actually work - checked, not assumed.

    python3 ready.py [--dir <task folder>]

Each line is ОК, НЕ (fix it now, before you go to bed) or СЛЕДИТЕ (cannot be read from here - one
thing for the person to look at). Nothing is changed on the computer: this only reads.
"""

import argparse
import glob
import json
import os
import platform
import shutil
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SYS = platform.system()
rows = []


def row(state, what, do=""):
    rows.append((state, what, do))


def sh(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def check_power():
    if SYS == "Darwin":
        out = sh(["pmset", "-g", "batt"])
        if "AC Power" in out:
            row("ОК", "Питание от сети.")
        elif out:
            row("НЕ", "Ноутбук на батарее — за ночь она сядет, и работа встанет.", "Подключите зарядку.")
        return
    if SYS == "Linux":
        bats = glob.glob("/sys/class/power_supply/BAT*")
        online = any(open(f).read().strip() == "1" for f in glob.glob("/sys/class/power_supply/*/online"))
        if not bats or online:
            row("ОК", "Питание от сети.")
        else:
            row("НЕ", "Ноутбук на батарее.", "Подключите зарядку.")
        return
    if SYS == "Windows":
        out = sh(["powershell", "-NoProfile", "-Command",
                  "(Get-CimInstance Win32_Battery).BatteryStatus"])
        if not out.strip() or out.strip() == "2":
            row("ОК", "Питание от сети.")
        else:
            row("НЕ", "Ноутбук на батарее.", "Подключите зарядку.")


def check_awake():
    home = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
    if SYS == "Windows":
        home = os.path.join(os.environ.get("LOCALAPPDATA", home), "nightcall")
    until = next((open(f, encoding="utf-8").read().strip() for f in glob.glob(os.path.join(home, "awake-*.until"))), "")
    if until:
        row("ОК", f"Кофеин включён до {until}.")
    else:
        row("НЕ", "Кофеин не включён — компьютер уснёт, как только вы отойдёте.",
            "Скилл /nightcall:awake 8 (или 12).")
    row("СЛЕДИТЕ", "Крышка ноутбука: закрытая крышка усыпляет компьютер, кофеин этого не отменяет.",
        "Оставьте крышку открытой; экран можно просто убавить до минимума.")


def check_updates():
    if SYS == "Darwin":
        v = sh(["defaults", "read", "/Library/Preferences/com.apple.SoftwareUpdate",
                "AutomaticallyInstallMacOSUpdates"]).strip()
        if v == "1":
            row("НЕ", "macOS сама ставит обновления и может перезагрузиться ночью.",
                "Настройки → Основные → Обновление ПО → (i) у «Автообновления» → выключите "
                "«Установка обновлений macOS» на эту ночь.")
        else:
            row("ОК", "macOS не перезагрузится ночью ради обновлений сама.")
    elif SYS == "Windows":
        row("СЛЕДИТЕ", "Windows Update умеет перезагружать ночью, и кофеин это не отменяет.",
            "Параметры → Центр обновления Windows → «Приостановить на 1 неделю».")
    elif SYS == "Linux":
        auto = any("Automatic-Reboot \"true\"" in open(f, errors="ignore").read()
                   for f in glob.glob("/etc/apt/apt.conf.d/*unattended*"))
        if auto:
            row("НЕ", "Автообновления настроены на перезагрузку.", "Отложите их на эту ночь.")
        else:
            row("ОК", "Автоперезагрузки после обновлений не видно.")


def check_network():
    try:
        socket.create_connection(("api.anthropic.com", 443), timeout=6).close()
        row("ОК", "Интернет есть, Claude достижим.")
    except OSError:
        row("НЕ", "Нет связи с Claude — ночью он ничего не сделает.", "Проверьте Wi-Fi; лучше кабель.")
    row("СЛЕДИТЕ", "Wi-Fi может отключаться в сне и при смене сети.",
        "Не уносите компьютер; VPN, который рвётся, лучше выключить на ночь.")


def check_disk(folder):
    free = shutil.disk_usage(folder or os.path.expanduser("~")).free / 1e9
    if free < 5:
        row("НЕ", f"Свободно всего {free:.1f} ГБ.", "Освободите место — ночью файлы растут.")
    else:
        row("ОК", f"Места на диске: {free:.0f} ГБ.")


def check_claude():
    if shutil.which("claude"):
        row("ОК", "Claude Code установлен.")
    else:
        row("НЕ", "Команда claude не найдена в этом окне.", "Запускайте ночь из Claude Code.")
    row("СЛЕДИТЕ", "Разрешения: ночью некому нажать «Да» — один вопрос остановит всю ночь.",
        "Перед уходом: Shift+Tab до режима auto (или accept edits), либо ночной цикл "
        "scripts/night-loop.sh. Проверьте на одном шаге, что вопросов не всплывает.")
    row("СЛЕДИТЕ", "Лимит подписки Claude: когда он кончается, работа ждёт до сброса.",
        "Наберите /usage и посмотрите, сколько осталось. Ночной цикл сам подождёт сброса и продолжит.")


def check_team(folder):
    out = sh([sys.executable, os.path.join(HERE, "team.py"), "list"], timeout=20)
    n = sum(1 for line in out.splitlines() if line.startswith("  "))
    if n:
        row("ОК", f"Других ИИ-программ по подписке найдено: {n}. Живы ли — покажет перекличка.")
    else:
        row("СЛЕДИТЕ", "Других ИИ-программ по подписке нет — запас: бесплатные ключи и веб-чаты в Chrome.",
            "Поставьте и войдите хотя бы в одну (codex, gemini/agy, kimi, grok, qwen) — или войдите "
            "в Chrome в 2–3 веб-чата (ChatGPT, Gemini, Kimi, DeepSeek, Meta AI).")
    seats = os.path.join(folder, "seats.json") if folder else ""
    if seats and os.path.exists(seats):
        try:
            data = json.load(open(seats, encoding="utf-8"))
        except ValueError:
            data = {}
        alive = [s for s in data.get("помощники", []) + data.get("ключи", []) if s.get("статус") == "жив"]
        web = [w for w in data.get("веб", []) if w.get("статус") == "жив"]
        if alive or web:
            row("ОК", f"Перекличка пройдена: живых программ/ключей {len(alive)}, веб-чатов в запасе {len(web)}.")
        else:
            row("НЕ", "Перекличка: ни одного живого помощника другой компании — ночь пройдёт только "
                "со своими критиками Claude.", "Войдите в программу или веб-чат сейчас и повторите перекличку.")
        if data.get("веб_когда") == "morning":
            row("ОК", "Веб-чаты: утром (web: morning) — ночью вопрос для них ляжет в утро-совет.md.")
        if not data.get("веб"):
            row("СЛЕДИТЕ", "Браузер ещё не проверен: веб-чаты — запас на случай лимитов.",
                "Скилл /nightcall:ready, шаг «Перекличка браузера» — пока вы рядом.")
    else:
        row("СЛЕДИТЕ", "Переклички ещё не было: живость помощников не проверена.",
            "Скилл /nightcall:ready делает её сам: программы, ключи и веб-чаты в Chrome.")


def check_folder(folder):
    """The safety net of the night: a restore point and the fence (course step "Fence and time machine"). Never a refusal:
    whatever is missing, `night.py begin` makes it by itself."""
    if not folder:
        return
    tags = sh(["git", "-C", folder, "tag", "--list", "nightcall-before-*"]).split()
    if tags:
        row("ОК", f"Точка возврата: есть (git-тег {sorted(tags)[-1]}) — утром всё можно откатить.")
    elif os.path.isdir(folder) and sh(["git", "-C", folder, "rev-parse", "--git-dir"]).strip():
        row("ОК", "Точка возврата: будет создана — night.py begin сделает коммит и тег «перед ночью».")
    else:
        row("ОК", "Точка возврата: будет создана — night.py begin сделает git init и коммит «перед ночью».")
    claude_md = os.path.join(folder, "CLAUDE.md")
    try:
        fenced = "nightcall:fence" in open(claude_md, encoding="utf-8").read()
    except OSError:
        fenced = False
    row("ОК", "Забор: " + ("есть — в CLAUDE.md папки «работать только в этой папке»." if fenced else
                                "будет вписан в CLAUDE.md папки при night.py begin."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="папка задачи")
    a = ap.parse_args()
    check_power(); check_awake(); check_updates(); check_network()
    check_disk(a.dir); check_claude(); check_team(a.dir); check_folder(a.dir)
    print("Перед ночью:")
    for state, what, do in rows:
        print(f"  {state:<8} {what}" + (f"\n           → {do}" if do else ""))
    bad = sum(1 for r in rows if r[0] == "НЕ")
    print(f"Итого: {bad} НЕ, {sum(1 for r in rows if r[0] == 'СЛЕДИТЕ')} СЛЕДИТЕ, "
          f"{sum(1 for r in rows if r[0] == 'ОК')} ОК.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
