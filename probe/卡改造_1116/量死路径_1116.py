# -*- coding: utf-8 -*-
"""★★★★★ 查「写死了一个**这个容器里不存在**的仓库路径」—— 1116 第十七轮新加。

★★★ 起因：本轮量术语/自述时顺手跑了一下 `probe/判决落卡_1111/判决落卡_1111.py`（成绩节的生成器），
   ★★★★★ 它**当场 rc=1 挂了**：`ROOT = "/home/claude/xing-agent-stock_data"` —— ★ 这个目录不存在
   （工单第一句就写着「仓库在 /home/claude/stock_data，旧工单写的 xing-agent-stock_data 不存在」）。
★★ 一扫全仓：**21 处 / 19 个 .py**，其中 13 处是顶层 `ROOT =` 赋值，还有 `engine/stages.py`
   的 `DEFAULT_DATA_ROOT`（★★★ 实测 `load_daily_json('AAPL')` 直接 FileNotFoundError）。

★★★★★ 为什么要紧（★ 两条，别缩短）：
   ① **规矩(80)③「有生成器的字改卡必须同时改生成器」在成绩节上是**执行不了的** ——
      ★★ 生成器跑不起来，就既不能重算、也不能拿它来验证 49 个 entries 的成绩节有没有被手改
      （★★★ 这正是台账 1116 代价⑫「成绩节手改闸④看不见」那个洞的另一半）。
   ② ★★ 好消息（★ 规矩：好消息不许夸大）：这一类**全是响亮地挂**（FileNotFoundError / rc=1），
      ★★★ **不是**「RC=0 但少写一半」那种闷声坏事（★ 日净值空目录那一类才是）。

★ 判法：只认**真的会当路径用**的写法（赋值 / sys.path.insert / cwd=），★★ 注释和文档字符串里的
   「跑法: cd …」单独记 🟡（★★★ 照着粘会失败，但不是代码在用）。
★ 只读不写。退出码 0 = 没 🔴；3 = 有 🔴。
"""
from __future__ import annotations
import os, re, io, json, sys

ROOT = os.environ.get("XING_SCAN_ROOT") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
# ★★ XING_SCAN_ROOT 只给**阳性对照**用（★ 在副本上种一行，真仓库一字节不动）
死路径 = "/home/claude/xing-agent-stock_data"
# ★★ 真的会当路径用的三种写法
在用 = [
    (re.compile(r"^\s*[A-Z_]{2,}\s*=\s*[\"']" + re.escape(死路径)), "顶层常量赋值"),
    (re.compile(r"sys\.path\.insert\([^)]*[\"']" + re.escape(死路径)), "sys.path.insert"),
    (re.compile(r"cwd\s*=\s*[\"']" + re.escape(死路径)), "subprocess cwd="),
]


def main() -> int:
    红, 黄, 扫 = [], [], 0
    for dp, dirs, fns in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for fn in sorted(fns):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dp, fn)
            扫 += 1
            for ln, 行 in enumerate(io.open(p, encoding="utf-8", errors="replace").read().splitlines(), 1):
                if 死路径 not in 行:
                    continue
                名 = next((n for r, n in 在用 if r.search(行)), None)
                项 = {"文件": os.path.relpath(p, ROOT), "行": ln, "原句": 行.strip()[:140]}
                if 名:
                    项["类"] = 名
                    项["★"] = ("★★★★★ 代码真的拿它当路径 —— ★ 这个目录在本容器不存在，"
                              "★★ 跑到这一行就 FileNotFoundError")
                    红.append(项)
                else:
                    项["★"] = "★★ 只在注释/文档字符串里（★ 照着粘命令会失败，代码本身没在用）"
                    黄.append(项)
    报 = {"★分母": {"扫了.py": 扫, "死路径": 死路径,
                 "这个目录存在吗": os.path.isdir(死路径)},
         "🔴代码在用": 红, "🟡只在注释里": 黄,
         "★★★★★本尺子看不见的": [
             "★ ① 拼出来的路径（`os.path.join('/home/claude', 'xing-agent-' + x)`）—— ★★ 一概看不见",
             "★ ② 别的写死路径（只查这一个字符串）",
             "★★★ ③ 它**不保证脚本能跑通** —— 只保证不是**这一个**路径把它挡住",
         ]}
    出 = os.environ.get("XING_OUT", "")
    if 出:
        io.open(出, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1))
    print(f"★ 分母：扫了 {扫} 个 .py · 死路径 `{死路径}`（存在吗：{os.path.isdir(死路径)}）")
    print(f"🔴 代码在用 {len(红)} 处 · 🟡 只在注释里 {len(黄)} 处")
    for h in 红:
        print(f"  [🔴{h['类']}] {h['文件']}:{h['行']} | {h['原句'][:100]}")
    for h in 黄[:10]:
        print(f"  [🟡注释] {h['文件']}:{h['行']}")
    if 出:
        print(f"★ 报告：{出}")
    return 3 if 红 else 0


if __name__ == "__main__":
    sys.exit(main())
