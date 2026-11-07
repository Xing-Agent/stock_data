#!/bin/bash
# ★ 一条臂一个进程（matrices.build 峰值 ~6GB）—— ★★ 被 OOM 杀了就重来，靠 arms/ 落盘续上
# ★★★ 同一时间只许一份（flock，规矩⑩）
# 用法: bash probe/自己赛道_1107/重启循环_1107.sh [次数]
cd "$(dirname "$0")/../.."
exec 9>/tmp/自己赛道_1107.lock; flock -n 9 || { echo "★★★ 已有一份在跑 —— 退出(规矩⑩)"; exit 0; }
N=${1:-40}
for k in $(seq 1 "$N"); do
  before=$(ls probe/自己赛道_1107/arms/*.json 2>/dev/null | wc -l)
  python3 probe/自己赛道_1107/跑自己赛道_1107.py
  rc=$?
  after=$(ls probe/自己赛道_1107/arms/*.json 2>/dev/null | wc -l)
  echo "★ 第 $k 轮：退出码 $rc，臂文件 $before → $after"
  [ "$after" -le "$before" ] && [ "$rc" -eq 0 ] && { echo "★ 没有新臂了，跑完"; break; }
done
