#!/bin/bash
# ★ 重启循环:被 OOM 杀了就重来,靠落盘的臂文件续上;同一时间只许一份(flock)
# ★★ 用法:bash probe/测仓位_1107/重启循环_1107.sh probe/测仓位_1107/跑测仓位_1107.py
cd "$(dirname "$0")/../.."
exec 9>/tmp/测仓位_1107.lock; flock -n 9 || { echo "★★★ 已有一份在跑 —— 退出(规矩⑩)"; exit 0; }
for k in $(seq 1 14); do
  python3 "$1" && { echo "★ 跑完"; break; }
  echo "★ 第 $k 次退出(码 $?),重启续跑"; sleep 3
done
