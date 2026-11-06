#!/bin/bash
# ★ 重启循环:被 OOM 杀了就重来,靠落盘的臂文件续上;同一时间只许一份(flock)
cd "$(dirname "$0")/../.."
exec 9>/tmp/挂件_1106.lock; flock -n 9 || { echo "已有一份在跑"; exit 0; }
for k in 1 2 3 4 5 6 7 8; do
  python3 "$1" && break
  echo "★ 第 $k 次退出(码 $?),重启"; sleep 3
done
