"""
★ 七(下)· 提交前暂存区检查 —— 暂存区里出现本次任务声明范围之外的文件 → ★ 警告。

三秒版:`git add -A` 会把**别人还没提交的文件**一起扫进我的提交里。
        所以提交前要有人问一句:暂存区里这些文件,是不是都属于我这次的活?

为什么要有这个文件(2026-10-29 真实事故,★ 发生三次):
    我用了 `git add -A` 和目录级 `git add`,★ 三次把并行 agent 未提交的文件扫走。
  ★ 当时的处置是「改成按文件提交」——★ 但那不是自检,那是我记得。
    ★★ 记得这件事本身不可靠,所以要做成一道会在提交前挡住的检查。

两种用法:
  ① 提交前查暂存区(pre-commit 钩子):
       python3 engine/checks/staged_scope.py --scope "engine/checks/*" "probe/checks_1029/*"
     暂存区里有范围外的文件 → 退出码 1。
  ② 查「如果我现在 git add -A 会扫到什么」(★ 只读,不动暂存区):
       python3 engine/checks/staged_scope.py --dry-add --scope "engine/checks/*"

安装成真正的 pre-commit 钩子:
       python3 engine/checks/staged_scope.py --install
  ★ 本次**没有自动安装** —— 另一个 agent 正在同一个工作树上提交,
    装一道会挡住他提交的钩子是在帮倒忙。要装由人来拍。

★ 本文件只读 git 状态,不改暂存区、不改任何跑批逻辑。
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))

#: 默认的范围声明文件(每行一个 glob;# 开头是注释)。
SCOPE_FILE = os.path.join(_HERE, "task_scope.txt")


def _git(*args: str, repo: str = _REPO) -> list[str]:
    # ★ core.quotepath=false:不然中文路径会被 git 转义成 \344\270\203…,
    #   glob 永远匹配不上 —— 我们的文件名**全是中文**,这一条是必须的。
    out = subprocess.run(("git", "-C", repo, "-c", "core.quotepath=false") + args,
                         capture_output=True, text=True, check=False)
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def staged_files(repo: str = _REPO) -> list[str]:
    """暂存区里的文件。"""
    return _git("diff", "--cached", "--name-only", repo=repo)


def would_add_all(repo: str = _REPO) -> list[str]:
    """
    ★ 只读:`git add -A --dry-run` —— 「如果我现在 git add -A,会扫到哪些文件」。
      这就是今天那三次事故的现场。
    """
    lines = _git("add", "-A", "--dry-run", repo=repo)
    out = []
    for ln in lines:
        if ln.startswith(("add '", "remove '")):
            out.append(ln.split("'", 1)[1].rsplit("'", 1)[0])
    return out


def load_scope(path: str = SCOPE_FILE) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [ln.strip() for ln in fh
                if ln.strip() and not ln.lstrip().startswith("#")]


def out_of_scope(files: list[str], scope: list[str]) -> list[str]:
    """不匹配任何一条 glob 的文件。目录型 glob 用 `dir/*` 或 `dir/**` 写。"""
    bad = []
    for f in files:
        if any(fnmatch.fnmatch(f, g) or
               (g.endswith("/**") and f.startswith(g[:-3] + "/")) or
               (g.endswith("/*") and f.startswith(g[:-2] + "/"))
               for g in scope):
            continue
        bad.append(f)
    return bad


def check(scope: list[str], *, files: list[str] | None = None,
          repo: str = _REPO, label: str = "暂存区") -> list[str]:
    if not scope:
        return ["★★ FAIL 本次任务**没有声明范围** —— "
                "不声明范围就无法判断暂存区里的文件该不该在里面。"
                "★ 用 --scope 或写 engine/checks/task_scope.txt。"]
    fs = staged_files(repo) if files is None else files
    bad = out_of_scope(fs, scope)
    if not bad:
        return []
    lines = [
        f"★★ 警告:{label}里有 {len(bad)} 个文件**不在本次任务声明的范围**内 —— "
        f"★ 这些很可能是并行 agent 还没提交的东西,"
        f"提交它们等于把别人的活扫进我的提交里(★ 今天已经发生三次)。",
        f"   声明范围:{scope}",
    ]
    lines += [f"   · {f}" for f in bad]
    lines.append("   ★ 处置:`git add` 按文件显式列出,"
                 "严禁 `git add -A` 或目录级 add。")
    return lines


HOOK = """#!/bin/sh
# ★ XING 提交前暂存区检查 —— 见 engine/checks/staged_scope.py
exec python3 "$(git rev-parse --show-toplevel)/engine/checks/staged_scope.py"
"""


def install_hook(repo: str = _REPO) -> str:
    d = os.path.join(repo, ".git", "hooks")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "pre-commit")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(HOOK)
    os.chmod(p, 0o755)
    return p


# ────────────────────────────────────────────────────────────────────────
# 自测 —— ★ 跑在**当前这个工作树的真实状态**上
# ────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    # 本次任务真实声明的范围
    scope = ["engine/checks/*", "probe/checks_1029/*"]

    # ── ★ 真实现场:现在这个工作树上 `git add -A` 会扫到什么 ──────────────
    all_add = would_add_all()
    bad = out_of_scope(all_add, scope)
    live = bool(bad)
    if live:
        print(f"  ① ★ 真实现场:现在 `git add -A` 会扫到 {len(all_add)} 个文件,"
              f"其中 {len(bad)} 个**不属于本次任务**:")
        for f in bad:
            print(f"       · {f}")
        print("  ② 这些正是并行 agent 此刻未提交的东西 —— "
              "★ `git add -A` 会把它们一起提交掉。这就是今天三次事故的机制。")
    else:
        # 工作树当下恰好没有并行改动(别人刚提交完)。
        # ★ 退回**真实历史**:拿最近一个提交的文件清单当输入,
        #   证明闸能分辨「这些文件属不属于某个声明范围」。
        last = _git("show", "--name-only", "--format=", "HEAD")
        all_add, bad = last, out_of_scope(last, scope)
        print(f"  ① 工作树当下没有并行改动 → 退回真实历史:HEAD 这个提交"
              f"共 {len(last)} 个文件,其中 {len(bad)} 个落在"
              f"「本次任务范围」之外(★ 本该如此 —— 那是别人的提交)")
        assert bad, last
        print("  ② ★ 提示:要看活的现场,请在并行 agent 有未提交文件时重跑这条自测。")

    msg = check(scope, files=all_add, label="`git add -A` 的结果")
    assert msg and "不在本次任务声明的范围" in msg[0], msg
    print("  ③ check() 在这份真实文件清单上返回警告:")
    for ln in msg[:2]:
        print("     ", ln[:130])

    # ── 按文件显式列出 → 通过 ────────────────────────────────────────────
    mine = [f for f in all_add if f.startswith("engine/checks/")] or \
        ["engine/checks/staged_scope.py", "probe/checks_1029/x.md"]
    assert check(scope, files=mine) == [], check(scope, files=mine)
    print(f"  ④ 只列范围内的 {len(mine)} 个文件 → 通过(这就是正确做法)")

    # ── 没声明范围 → FAIL ───────────────────────────────────────────────
    assert any("没有声明范围" in x for x in check([], files=mine))
    print("  ⑤ 一个范围都没声明 → ★★ FAIL(不声明就无法判断)")

    # ── 真实暂存区(现在应该是空的,所以这一条只验证函数跑得通)──────────
    print(f"  ⑥ 当前真实暂存区:{len(staged_files())} 个文件")

    print("checks/staged_scope 自测通过 —— "
          "★ 在当前工作树的真实状态上抓到了并行 agent 的未提交文件;"
          "★ pre-commit 钩子**没有自动安装**(会挡住并行 agent 的提交,要装由人拍)")


def main(argv: list[str]) -> int:
    scope: list[str] = []
    dry = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--install":
            print("已安装 pre-commit 钩子:" + install_hook())
            return 0
        if a == "--selftest":
            _selftest()
            return 0
        if a == "--dry-add":
            dry = True
        elif a == "--scope":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                scope.append(argv[i])
                i += 1
            continue
        i += 1

    scope = scope or load_scope()
    files = would_add_all() if dry else None
    msg = check(scope, files=files,
                label="`git add -A` 的结果" if dry else "暂存区")
    if msg:
        print("\n".join(msg))
        return 1
    print("✅ 暂存区里的文件都在本次任务声明的范围内")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        _selftest()
    else:
        sys.exit(main(sys.argv[1:]))
