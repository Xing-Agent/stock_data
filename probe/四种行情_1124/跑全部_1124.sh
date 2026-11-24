#!/bin/bash
# 依次跑：两段 × 基准设定，再跑邻点（慢关 1 / 5 天、缺格改算震荡）。一次一个进程，做完的跳过。
cd "$(dirname "$0")"
for seg in 二 一; do
  for cfg in "3 3" "1 3" "5 3" "3 2"; do python3 四种行情_1124.py $seg $cfg; done
done
echo ALLDONE
