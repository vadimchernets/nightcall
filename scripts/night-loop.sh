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

folder=${1:?"Укажите папку задачи: bash night-loop.sh <папка> [часы]"}
hours=${2:-8}
case "$hours" in ''|*[!0-9]*) echo "Часы — целое число, например 8 или 12."; exit 2;; esac
[ -f "$folder/PLAN.md" ] || { echo "В $folder нет PLAN.md — сначала /nightcall:start пишет план."; exit 2; }
command -v claude >/dev/null 2>&1 || { echo "Команда claude не найдена."; exit 3; }

here=$(cd "$(dirname "$0")" && pwd)
folder=$(cd "$folder" && pwd)
mode=${NIGHTCALL_PERMISSION_MODE:-auto}
max_rounds=${NIGHTCALL_MAX_ROUNDS:-60}
limit_wait=${NIGHTCALL_LIMIT_WAIT:-900}
end=$(( $(date +%s) + hours * 3600 ))
log="$folder/night-loop.log"

bash "$here/awake.sh" "$hours" | tee -a "$log"
echo "$(date '+%F %T') ночной цикл: до $(date -r "$end" '+%H:%M' 2>/dev/null || date -d "@$end" '+%H:%M'), режим $mode" | tee -a "$log"

prompt="Ты работаешь ночью по плагину nightcall, человек спит — ничего у него не спрашивай.
Папка задачи: $folder
1. Прочитай TASK.md, PLAN.md, PROGRESS.md (и seats.json, если есть).
2. Возьми ПЕРВЫЙ несделанный шаг из PLAN.md. Сделай его целиком, проверь по его критерию «готово».
3. Самокритика: перечитай результат глазами строгого проверяющего; если шаг важный — спроси живого
   помощника: python3 \"$here/team.py\" ask --seats \"$folder/seats.json\" --dir \"$folder\" - (вопрос на вход).
   Исправь найденное один раз.
4. Допиши в PROGRESS.md: время (date), шаг, что сделано, как проверено, что осталось, спорные решения
   в раздел «Проверить утром». Если папка под git — один коммит на шаг.
5. Если все шаги сделаны — напиши MORNING.md по скиллу nightcall:morning.
Сделай ОДИН шаг и заверши работу."

round=0
while :; do
  now=$(date +%s)
  [ "$now" -lt "$end" ] || { echo "$(date '+%F %T') время вышло" | tee -a "$log"; break; }
  [ -f "$folder/MORNING.md" ] && { echo "$(date '+%F %T') MORNING.md готов — ночь закончена" | tee -a "$log"; break; }
  [ -f "$folder/STOP" ] && { echo "$(date '+%F %T') найден STOP — останавливаюсь" | tee -a "$log"; break; }
  [ "$round" -lt "$max_rounds" ] || { echo "$(date '+%F %T') потолок $max_rounds кругов" | tee -a "$log"; break; }
  round=$((round + 1))
  echo "$(date '+%F %T') круг $round" | tee -a "$log"
  out=$(cd "$folder" && claude -p "$prompt" --permission-mode "$mode" ${NIGHTCALL_MODEL:+--model "$NIGHTCALL_MODEL"} 2>&1)
  rc=$?
  printf '%s\n' "$out" | tail -20 >> "$log"
  if printf '%s' "$out" | grep -qiE "usage limit|limit reached|rate.?limit|hit your limit|resets? (at|in)"; then
    echo "$(date '+%F %T') лимит подписки — жду $((limit_wait / 60)) мин и пробую снова" | tee -a "$log"
    round=$((round - 1))
    sleep "$limit_wait"
  elif [ "$rc" -ne 0 ]; then
    echo "$(date '+%F %T') круг закончился с кодом $rc — через минуту следующий" | tee -a "$log"
    sleep 60
  fi
done

if [ ! -f "$folder/MORNING.md" ]; then
  (cd "$folder" && claude -p "Ночь по плагину nightcall закончилась. Папка: $folder. Напиши MORNING.md: сделано / не сделано / что проверить утром — строго по PROGRESS.md и git log, ничего не придумывая." --permission-mode "$mode" ${NIGHTCALL_MODEL:+--model "$NIGHTCALL_MODEL"} >> "$log" 2>&1)
fi
echo "$(date '+%F %T') цикл завершён. Отчёт: $folder/MORNING.md" | tee -a "$log"
