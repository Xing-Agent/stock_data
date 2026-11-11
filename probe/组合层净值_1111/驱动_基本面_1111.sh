#!/usr/bin/env bash
# ★★★★★ 一条臂一个进程（★ 避开 OOM —— 见 存净值_基本面_1111.py 的 main() 注释）
set -u
cd /home/claude/xing-agent-stock_data
LOG=probe/组合层净值_1111/驱动日志_1111.txt
: > "$LOG"
好=0; 坏=0
for i in $(seq 0 32); do
  s=$(date +%s)
  python3 probe/组合层净值_1111/存净值_基本面_1111.py --arm "$i" \
      >> "$LOG" 2>&1
  rc=$?
  e=$(date +%s)
  if [ $rc -eq 0 ]; then 好=$((好+1)); else 坏=$((坏+1)); fi
  echo "=== arm $i 退出码 $rc 耗时 $((e-s))s（累计 好=$好 坏=$坏）===" >> "$LOG"
done
echo "★★★★★ 全部跑完：好=$好 坏=$坏" >> "$LOG"
