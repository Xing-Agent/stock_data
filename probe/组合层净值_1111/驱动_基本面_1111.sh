#!/usr/bin/env bash
# ★★★★★ 一条臂一个进程（避 OOM）。
# ★★★ 判据/写法改过一次：第一版用了**中文变量名**（好/坏）——
#   bash 不支持中文标识符，`$((好+1))` 直接算术报错，循环只跑了第 0 条就断。
#   ★★ 而我们**早有规矩②**：shell 里不许用中文。这次是第二次踩。
#   ✅ 现行版：全部 ASCII 变量名，并把每条的退出码和耗时都落日志。
set -u
cd /home/claude/xing-agent-stock_data
LOG=probe/组合层净值_1111/驱动日志_1111.txt
FROM=${1:-0}; TO=${2:-32}
: > "$LOG"
ok=0; bad=0
for i in $(seq "$FROM" "$TO"); do
  s=$(date +%s)
  python3 probe/组合层净值_1111/存净值_基本面_1111.py --arm "$i" >> "$LOG" 2>&1
  rc=$?
  e=$(date +%s)
  if [ "$rc" -eq 0 ]; then ok=$((ok+1)); else bad=$((bad+1)); fi
  echo "=== arm $i rc=$rc ${s}->${e} dur=$((e-s))s cum_ok=$ok cum_bad=$bad ===" >> "$LOG"
done
echo "ALL DONE ok=$ok bad=$bad" >> "$LOG"
