#!/bin/bash
# ★ 重启循环:被 OOM 杀了就重来,靠落盘的分片续上;同一时间只许一份(flock)
# ★★ 用法:bash probe/PEAD_1107/重启循环_1107.sh
cd "$(dirname "$0")/../.."
exec 9>/tmp/PEAD_1107.lock; flock -n 9 || { echo "★★★ 已有一份在跑 —— 退出(规矩⑩)"; exit 0; }
for k in $(seq 1 30); do
  python3 probe/PEAD_1107/先数次数_1107.py && { echo "★ 跑完"; break; }
  echo "★ 第 $k 次退出(码 $?),重启续跑"; sleep 3
done
