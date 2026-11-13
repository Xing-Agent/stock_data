# -*- coding: utf-8 -*-
"""★★★★★ 出包脚本 —— ★ 规矩 71 ② 要的那道「出包前的机器检查」就装在这里。

★★ 三秒版：**先过六道闸，全过了才打 zip**。★★★ 任何一道没过 → 不打包、退出码 1。
   ① git 状态（工作区脏 / HEAD 记下来）
   ② 卡数 · 文件数
   ③ 共用边界 6 个文件 × 每张卡 md5 全同（★★ 一个分叉都不许有）
   ④ **判据有没有被动** —— ★★★★★ 基线**从 git 解**，不用另存目录（《92》1113 八②）
   ⑤ 体检红牌 0（★ 黄牌只打印，不拦）
   ⑥ **待合入项清单是否清空** —— ★★★ 规矩 71 ②，清单在 `手册/待合入项清单.md`

★ 为什么要做成脚本：★★★ 规矩 71 的原话是「**规则管不住，格子才管得住**」。
  ★★ 上一版（V2.5.8）的 zip 是手打的，这六件全靠记性 —— ★★★★★ 记性正是出事的那一次的原因。

★ 用法：
    python3 probe/出包_1113/出包_1113.py                 # 只查不打包（★★ 默认 dry-run）
    XING_PACK=1 XING_VER=V2.5.9 python3 probe/出包_1113/出包_1113.py   # 查完真打包
★★ 逃生门（★★★ 撞到了先想想是不是闸在干活，别顺手就开）：
    XING_ALLOW_DIRTY=1     工作区脏也让过
    XING_ALLOW_CRIT=1      判据被动也让过（★★★★★ 这个要走 Lin，《130》A 格）
    XING_BASELINE_REF=<commit>  指定比哪一版
★ 退出码：0 = 全过；1 = 有闸没过。
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
卡目录 = os.path.join(ROOT, "skills_v2")
清单路径 = os.path.join(ROOT, "手册", "待合入项清单.md")
体检脚本 = os.path.join(ROOT, "probe", "卡改造_1108", "体检_1109.py")

问题 = []        # ★ 拦包的
提醒 = []        # ★ 只打印的


def 跑(cmd, cwd=ROOT):
    p = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def md5(path):
    return hashlib.md5(io.open(path, "rb").read()).hexdigest()


def 闸1_git():
    rc, head = 跑(["git", "rev-parse", "HEAD"])
    rc2, 脏 = 跑(["git", "status", "--porcelain"])
    head = head.strip()
    脏行 = [x for x in 脏.splitlines() if x.strip()]
    print(f"① git：HEAD = {head[:9]}　未提交 {len(脏行)} 处")
    if 脏行 and not os.environ.get("XING_ALLOW_DIRTY"):
        问题.append(f"★★★ 工作区有 {len(脏行)} 处未提交改动 —— "
                    f"★ 打出来的包和仓库对不上（逃生门 XING_ALLOW_DIRTY=1）："
                    + "；".join(x.strip()[:60] for x in 脏行[:5]))
    elif 脏行:
        提醒.append(f"★★ 工作区脏 {len(脏行)} 处，★ 已用 XING_ALLOW_DIRTY 放过")
    return head


def 闸2_数数():
    卡 = sorted(d for d in os.listdir(卡目录)
                if os.path.isdir(os.path.join(卡目录, d)))
    文件 = [os.path.join(r, f) for r, _, fs in os.walk(卡目录) for f in fs]
    print(f"② 数数：卡 {len(卡)} 张 · 文件 {len(文件)} 个")
    期望 = os.environ.get("XING_EXPECT_CARDS")
    if 期望 and int(期望) != len(卡):
        问题.append(f"★★★ 卡数对不上：期望 {期望}，实际 {len(卡)}")
    for d in 卡:
        if not os.path.exists(os.path.join(卡目录, d, "SKILL.md")):
            问题.append(f"★★★ `{d}` 没有 SKILL.md —— ★ 这张卡装上去是哑的")
    return 卡, 文件


def 闸3_共用边界(卡):
    份 = {}
    for d in 卡:
        shared = os.path.join(卡目录, d, "references", "shared")
        if not os.path.isdir(shared):
            continue
        for f in sorted(os.listdir(shared)):
            份.setdefault(f, {})[d] = md5(os.path.join(shared, f))
    if not 份:
        问题.append("★★★ 一张卡都没找到 references/shared —— ★ 这道闸等于没查，先看路径对不对")
        return
    坏 = 0
    for f, m in sorted(份.items()):
        不同 = sorted(set(m.values()))
        标 = "✅" if len(不同) == 1 else "🔴"
        print(f"③ 共用边界 {标} {f}：{len(m)} 份 · {len(不同)} 种 md5")
        if len(不同) > 1:
            坏 += 1
            头 = {}
            for 卡名, h in m.items():
                头.setdefault(h, []).append(卡名)
            少 = sorted(头.items(), key=lambda kv: len(kv[1]))[0]
            问题.append(f"★★★★★ 共用边界 `{f}` 分叉成 {len(不同)} 种 —— "
                        f"★ 少数派那几张：{'、'.join(少[1][:6])}")
    if not 坏:
        print(f"③ 共用边界：{len(份)} 个文件，★★ 每个都是全卡同一份 ✅")


def 闸4_5_体检(head):
    """★★★★★ 判据被动 + 红牌 —— ★ 基线从 git 解，不留目录。"""
    rc, out = 跑(["git", "log", "--format=%H", "--", "skills_v2"])
    历史 = [x for x in out.split() if x]
    基线ref = os.environ.get("XING_BASELINE_REF") or ""
    if not 基线ref:
        # ★★★★★ 1113 当场改掉的一个坑：原来直接取「上一个动过 skills_v2 的 commit」——
        #   ★ 但 HEAD 常常不动卡（比如只改台账），★★ 那个 commit 的卡**就是现在这份**
        #   → ★★★ 自己跟自己比，**永远报 0 条**，★★★★★ 看起来过闸，其实闸没干活。
        # ★★ 改法：**跳过所有「卡和现在一模一样」的 commit**，取第一个真的不一样的。
        rc3, 当前树 = 跑(["git", "rev-parse", "HEAD:skills_v2"])
        for c in 历史:
            rc5, t = 跑(["git", "rev-parse", f"{c}:skills_v2"])
            if rc5 == 0 and t.strip() and t.strip() != 当前树.strip():
                基线ref = c
                break
        if not 基线ref and 历史:
            基线ref = 历史[-1]
    if not 基线ref:
        提醒.append("★★ 没找到上一版 commit → 判据被动这一项没查")
        基线目录 = ""
    else:
        基线目录 = tempfile.mkdtemp(prefix="xing_baseline_")
        rc, out = 跑(f"git archive {基线ref} skills_v2 | tar -x -C {基线目录}")
        if rc != 0 or not os.path.isdir(os.path.join(基线目录, "skills_v2")):
            提醒.append(f"★★ 解基线失败（{基线ref[:9]}）→ 判据被动没查：{out[:200]}")
            基线目录 = ""
        else:
            基线目录 = os.path.join(基线目录, "skills_v2")
            print(f"④ 判据基线：{基线ref[:9]}（从 git 解出，不留目录）")

    env = dict(os.environ)
    env["XING_TAG"] = os.environ.get("XING_TAG", "出包_" + head[:7])
    if 基线目录:
        env["XING_BASELINE"] = 基线目录
    p = subprocess.run([sys.executable, 体检脚本], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    报路径 = os.path.join(ROOT, "手册", f"体检_{env['XING_TAG']}.json")
    if not os.path.exists(报路径):
        问题.append(f"★★★ 体检没出报告 —— ★ 它自己先挂了：{p.stdout.decode('utf-8','replace')[-300:]}")
        return
    报 = json.loads(io.open(报路径, encoding="utf-8").read())
    被动 = 报.get("🔴判据被动", [])
    红 = sum(len(报.get(k, [])) for k in 报 if k.startswith("🔴"))
    黄 = sum(len(报.get(k, [])) for k in 报 if k.startswith("🟡"))
    print(f"④ 判据被动：{len(被动)} 条　⑤ 体检：🔴 红牌 {红} · 🟡 黄牌 {黄}")
    if 被动:
        for x in 被动[:6]:
            print("   ", json.dumps(x, ensure_ascii=False)[:160])
        if os.environ.get("XING_ALLOW_CRIT"):
            提醒.append(f"★★★★★ 判据被动 {len(被动)} 条，★ 已用 XING_ALLOW_CRIT 放过 —— "
                        f"★★★ 这件按《130》A 格**要走 Lin**，别默默出包")
        else:
            问题.append(f"★★★★★ 判据被动 {len(被动)} 条 —— ★★★ 数字门槛/取前N/周期/止损刻度被改过，"
                        f"★ 这是《130》A 格「要 Lin」那一类，**不许顺手出包**")
    if 红 - len(被动) > 0:
        问题.append(f"★★★ 体检红牌 {红 - len(被动)} 张（判据以外）—— ★ 先看 {报路径}")
    if 黄:
        提醒.append(f"★★ 黄牌 {黄} 张（不拦包，★ 但要人看一眼）：{报路径}")


def 闸6_待合入项():
    """★★★★★ 规矩 71 ② —— ★ 各组报过的改动，是不是都进包了。"""
    if not os.path.exists(清单路径):
        问题.append(f"★★★★★ 没有 `手册/待合入项清单.md` —— ★ 规矩 71 ② 的检查**无处可查**，"
                    f"★★ 先把清单建起来（这道闸不许空过）")
        return
    txt = io.open(清单路径, encoding="utf-8").read()
    拦 = re.findall(r"^\s*-\s*\[\s\]\s*(.+)$", txt, re.M)
    已 = re.findall(r"^\s*-\s*\[[xX]\]\s*(.+)$", txt, re.M)
    挂 = "## 挂着" in txt
    print(f"⑥ 待合入项：未合入 {len(拦)} 条 · 已合入 {len(已)} 条"
          + ("　★ 另有「挂着·不拦包」一节" if 挂 else ""))
    for x in 拦[:8]:
        print("   🔴", x[:120])
    if 拦:
        问题.append(f"★★★★★ 待合入项还剩 {len(拦)} 条没合 —— ★★★ 规矩 71 ②：**这些改动不在包里**，"
                    f"★ 各组测过的东西在正式包里会退回去（就是上次 F02/F06/F08/M01 那件）")


def 打包(卡, 文件):
    ver = os.environ.get("XING_VER", "")
    if not ver:
        问题.append("★★★ 要打包就得给版本号：XING_VER=V2.5.9")
        return None
    日 = os.environ.get("XING_DATE", "1113")
    名 = f"XING_Skills_{ver}_{len(卡)}张_{日}"
    出 = os.path.join(ROOT, "dist", 名 + ".zip")
    os.makedirs(os.path.dirname(出), exist_ok=True)
    清 = os.path.join(ROOT, "dist", 名 + "_md5清单.txt")
    with io.open(清, "w", encoding="utf-8") as fh:
        for p in sorted(文件):
            fh.write(f"{md5(p)}  {os.path.relpath(p, ROOT)}\n")
    rc, out = 跑(f"cd {ROOT} && zip -q -r '{出}' skills_v2 && echo OK")
    if rc != 0:
        问题.append(f"★★★ zip 失败：{out[:300]}")
        return None
    sha = hashlib.sha256(io.open(出, "rb").read()).hexdigest()
    print(f"\n📦 {出}\n   SHA-256 {sha}\n   md5 清单 {清}（{len(文件)} 行）")
    return 出


def main():
    print("=" * 60)
    print("★★★★★ 出包前机器检查（规矩 71 ②）")
    print("=" * 60)
    head = 闸1_git()
    卡, 文件 = 闸2_数数()
    闸3_共用边界(卡)
    闸4_5_体检(head)
    闸6_待合入项()
    print("-" * 60)
    for x in 提醒:
        print("🟡", x)
    if 问题:
        print(f"\n🔴 **{len(问题)} 道闸没过 → 不打包**")
        for x in 问题:
            print("  ·", x)
        return 1
    print("\n✅ 六道闸全过")
    if os.environ.get("XING_PACK"):
        打包(卡, 文件)
        if 问题:
            for x in 问题:
                print("  ·", x)
            return 1
    else:
        print("★★ 这是只查不打包（★ 真要打包：XING_PACK=1 XING_VER=V2.5.9）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
