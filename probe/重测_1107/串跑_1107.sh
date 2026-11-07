#!/usr/bin/env bash
# ★★★ 重测串跑链 —— ★ 一族一个进程，跑完就退出把内存还给系统。
#
# ★★ 为什么要这样：22 年 × 3,858 只整批跑会 OOM（机器 7 GB，今天栽了三次，exit 137）。
# ★★★ 可续跑：每条臂的结果按 label 的 sha256 存成单独文件，
#   已经有结果的臂会被直接跳过 —— 所以这个脚本**可以反复重跑，不会重复算**（规矩⑩）。
#
# ★ 顺序（《102》第七节）：
#   1. B 段 2015~2025 四族
#   2. A 段 2004~2014 四族   ← ★★ 两段齐了才能做滚动前推（A 段挑 / B 段验）
set -u
cd /home/claude/xing-agent-stock_data || exit 1
LOG=/tmp/claude-0/-home-claude/e6b5eede-2545-5921-9bbc-5820cecf2c9c/scratchpad/串跑_1107.log

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

say "★★★ 串跑开始 —— 口径：全收益（分红再投，两侧同口径，《104》拍板）"

for WIN in "B_2015到2025|2015-01-01|2025-12-31" "A_2004到2014|2004-01-02|2014-12-31"; do
  IFS='|' read -r NAME START END <<< "$WIN"
  for FAM in 大波段 突破 震荡; do
    say "▶▶ $NAME · $FAM 开跑"
    XING_WIN_NAME="$NAME" XING_WIN_START="$START" XING_WIN_END="$END" XING_FAM="$FAM" \
      python3 probe/重测_1107/跑重测_1107.py >> "$LOG" 2>&1
    RC=$?
    if [ $RC -eq 0 ]; then
      say "✓✓ $NAME · $FAM 跑完"
    elif [ $RC -eq 137 ]; then
      # ★★★ 不要静默跳过 —— OOM 必须大声说出来（规矩⑯ 响亮失败）
      say "⚠⚠ $NAME · $FAM **被 OOM 杀了（137）** —— 这一族没跑完，不许进结论"
    else
      say "⚠⚠ $NAME · $FAM 退出码 $RC —— 不许进结论"
    fi
    say "   ★ 当前已完成臂数：$(ls probe/重测_1107/arms_1107/ 2>/dev/null | wc -l)"
  done
done

say "★★★ 串跑结束 —— 已完成臂数：$(ls probe/重测_1107/arms_1107/ 2>/dev/null | wc -l)"
say "★ 下一步（要人来做判断的）：配对检验（规矩㊸v2）+ 条件 alpha 交互项 + 持仓画像"
