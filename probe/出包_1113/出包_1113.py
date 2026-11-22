# -*- coding: utf-8 -*-
"""★★★★★ 出包脚本 —— ★ 规矩 71 ② 要的那道「出包前的机器检查」就装在这里。

★★ 三秒版：**先过十二道闸，全过了才打 zip**。★★★ 任何一道没过 → 不打包、退出码 1。
   ① git 状态（工作区脏 / HEAD 记下来）
   ② 卡数 · 文件数
   ③ 共用边界 6 个文件 × 每张卡 md5 全同（★★ 一个分叉都不许有）
   ④ **判据有没有被动** —— ★★★★★ 基线**从 git 解**，不用另存目录（《92》1113 八②）
   ⑤ 体检红牌 0（★ 黄牌只打印，不拦）★★★ 注意：体检的**泄漏/术语/自述**三格仍是**窄口径（只 SKILL.md）**
      → ★★ 泄漏的**全仓**那一份在**闸⑩**（1116 新加）
      → ★★★★★ **术语 / 自述 1116 第十七轮量过了**：全仓复量「术语」窄 1 → 全仓 2（只多 1 条）·
        「自述」那三条判据全仓 **0 处** → ★★★ **扩覆盖买到的是 0，所以没扩**（★ 不是没量）；
        ★★ 「自述」另外三类（本卡N行 / 第N行 / N张卡）本来就在**闸⑦**全仓扫。
   ⑥ **待合入项清单是否清空** —— ★★★ 规矩 71 ②，清单在 `手册/待合入项清单.md`
   ⑦ **自述里的行号和数目对不对** —— ★★★★★ 1114 新加：「本卡 N 行」/「第 N 行」指路 /「N 张卡」
      ★★ 起因：体检 ⑤ 报「自述不符 0」，★★★ 但它只查三样，**不查行号** ——
      ★ 1114 实测：6 张卡行数自述全错、6 处行号指到空行/围栏、1 处规模自述还写「八张卡」。
   ⑧ 保留词「失效位」解释在不在旁边（规矩 79）· ⑨ 6.12 其余 11 行禁词（规矩 78）
   ⑩ **泄漏全仓** —— ★★★★★ 1116 新加：内部口吻 / 仓库路径，扫**全部 489 个 .md**
      ★★ 起因：闸④⑤ 的泄漏那一格只喂 39 个 SKILL.md（覆盖 8%）；★★★ 1115 的「60 处」是错数（错号 #117）。
   ⑪ **写死的死路径** —— ★★★★★ 1116 第十七轮新加：`/home/claude/xing-agent-stock_data`（★ 本容器不存在）
      ★★ 起因：本轮跑成绩节的生成器 `判决落卡_1111.py`，**当场 rc=1** —— ROOT 写死在那个不存在的目录上。
      ★★★ 一扫全仓：**19 处 / 17 个 .py 代码真在用**（含 `engine/stages.py` 的 DEFAULT_DATA_ROOT）。
      ★★★★★ 为什么这是闸不是小事：规矩(80)③「有生成器的字改卡必须同时改生成器」——
        ★ 生成器跑不起来，这条规矩在成绩节上**执行不了**（★★ 既不能重算也不能验证有没有被手改）。

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
import glob
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


def 闸7_自述行号():
    """★★★★★ 1114 新加 —— ★ 顶部入口块的行号指路准不准（体检 ⑤ 不查这个）。

    ★★ 为什么要拦包：那些「先看这一条」的入口块是 11-12 为「模型走不到正文中部」加的，
      ★★★ 它们靠行号指路；★★★★★ 文件一长，行号就指到空行 —— **修位置问题的东西自己坏了**。
    """
    脚本 = os.path.join(ROOT, "probe", "卡改造_1114", "查自述_行号与数目_1114.py")
    if not os.path.isfile(脚本):
        问题.append("★★★ 缺 `probe/卡改造_1114/查自述_行号与数目_1114.py` —— ★ 闸 7 无处可查")
        return
    env = dict(os.environ, XING_TAG=os.environ.get("XING_TAG", "出包"))
    p = subprocess.run([sys.executable, "-I", 脚本], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace")
    头 = out.splitlines()[0] if out else "(没输出)"
    print(f"⑦ 自述行号：{头}")
    if p.returncode == 3:
        问题.append("★★★★★ 自述行号/数目有 🔴 —— ★ 全文见上面那几行和 `手册/查自述_行号与数目_*.json`")
        for L in out.splitlines()[1:9]:
            print("   ", L[:170])
    elif p.returncode != 0:
        问题.append(f"★★★ 闸 7 自己挂了（rc={p.returncode}）：{out[-300:]}")


# ★★★★★ 保留词表（规矩 79）—— ★ 现在只有一个词。★★★ 加词只加这里，别动尺子。
# ★★ 「保留词」= 允许出现，但**面向用户第一次出现必须跟一句解释**（和 6.12 其余 11 行的「禁词」不是一回事）。
保留词 = [
    ("失效位", "跌破它，当初做这笔的理由就不在了"),
]


def 闸8_保留词():
    """★★★★★ 1115 第十三轮新加（规矩 79 装进闸）—— ★ 闸⑦ 旁边一格。

    ★★★ 为什么是单独一道而不是塞进体检：6.12 这张表有**两类行**——
      ★ 11 行是「不许出现」（grep 禁词就够，规矩 78）；
      ★★★★★ 「失效位」这一行是「**必须跟解释**」→ 查的是**解释在不在旁边**，禁词尺子管不到。
    ★★ 这道闸不自己判，★★★ 它调 1115 那把量过的尺子（规矩 79 的三条都在尺子里：
      双向窗口 · 先剔内部写法再定「第一次」· 人核结论钉死在脚本里），只负责**把 🔴 变成不打包**。
    """
    脚本 = os.path.join(ROOT, "probe", "卡改造_1115", "量失效位解释_1115.py")
    if not os.path.isfile(脚本):
        问题.append("★★★ 缺 `probe/卡改造_1115/量失效位解释_1115.py` —— ★ 闸 8 无处可查")
        return
    for 词, 要的解释 in 保留词:
        安全名 = "".join(ch if ch.isalnum() else "_" for ch in 词)
        出 = os.path.join(tempfile.gettempdir(), f"xing_闸8_{安全名}.json")
        env = dict(os.environ, XING_RESERVED_WORD=词, XING_OUT=出)
        p = subprocess.run([sys.executable, "-I", 脚本], cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout.decode("utf-8", "replace")
        if p.returncode != 0 or not os.path.isfile(出):
            问题.append(f"★★★ 闸 8 自己挂了（词「{词}」· rc={p.returncode}）：{out[-300:]}")
            continue
        d = json.load(io.open(出, encoding="utf-8"))
        结果 = d.get("结果", [])
        红 = [r for r in 结果 if r["判"].startswith("🔴")]
        黄 = [r for r in 结果 if r["判"].startswith("🟡")]
        print(f"⑧ 保留词「{词}」：{len(结果)} 张卡用到 · "
              f"面向用户 {sum(r['面向用户数'] for r in 结果)} 处 · 🔴 {len(红)} · 🟡 {len(黄)}")
        # ★★★★★ 和闸③ 同一个坑：**一处都没捞到 ≠ 干净**，更可能是尺子没咬住（路径/包名错了）。
        if not 结果:
            问题.append(f"★★★★★ 闸 8：全仓一处「{词}」都没找到 —— ★★★ 这道闸等于没查，"
                        f"★ 先看 XING_CARDS/路径对不对（★★ 1115 两次证实：报 0 先怀疑尺子）")
            continue
        for r in 红:
            h = r["第一次"]
            print(f"   🔴 {r['卡']} → {h['文件']}:{h['行号']} [{h['位置']}] {h['原文'][:70]}")
        if 红:
            问题.append(f"★★★★★ 闸 8：{len(红)} 张卡「{词}」**面向用户第一次出现前后都没跟解释** —— "
                        f"★★★ 6.12 要求的是那句「{要的解释}」；"
                        f"★★ 改法见《198》二节（箱体按同箱众数宽度补齐 · 正文接在用户原话句尾）")
        for r in 黄:
            提醒.append(f"★★ 闸 8：{r['卡']}「{词}」只匹到宽口径（{r['判']}）—— ★ 要人看一眼是不是真解释")
        if d.get("人核表失配"):
            失 = [e for e in d.get("人核表", []) if e["配上几处"] == 0]
            提醒.append(f"★★★ 闸 8：规矩79 的人核钉死表有 {len(失)} 条配不上了"
                        f"（{'; '.join(e['文件'] + '←' + e['片段'][:18] for e in 失[:3])}）—— "
                        f"★★ 那几处要么被改了措辞、要么被删了，★★★ 内部/面向用户的归类要重核一遍")


def 闸9_禁词():
    """★★★★★ 1115 第十四轮新加（规矩 78 装进闸）—— ★ 闸⑧ 旁边一格，补上 6.12 的**另外 11 行**。

    ★★★ 分工：闸⑧ 管「失效位」（保留词，查解释在不在旁边）；★★ 本闸管其余 11 行禁词，
      查的是「**有没有出现在用户会看到的那一屏**」。
    ★★★★★ 为什么不自己 grep：1114 那版直接 grep 报 **155 处 · 92% 是假的**（错号 #109/#110）。
      ★ 所以本闸和闸⑦⑧ 同一个写法 —— **判断只许有一份实现**：subprocess 调
      `probe/卡改造_1115/量禁词_1115.py`（规矩 78 的三条都在尺子里：
       引号只是其中一种命中条件 · 形态分类要打印 · 看不见哪一类要写明），
      ★★ 本闸只负责**把 🔴 变成不打包 + rc=1**。
    ★★★ 1115 第十四轮装之前先在现状上量过：🔴 **0 处**（★ 同一轮刚把 49 处「组合层最大回撤 %」改掉）。
    """
    脚本 = os.path.join(ROOT, "probe", "卡改造_1115", "量禁词_1115.py")
    if not os.path.isfile(脚本):
        问题.append("★★★ 缺 `probe/卡改造_1115/量禁词_1115.py` —— ★ 闸 9 无处可查")
        return
    出 = os.path.join(tempfile.gettempdir(), "xing_闸9_禁词.json")
    env = dict(os.environ, XING_OUT=出)
    p = subprocess.run([sys.executable, "-I", 脚本], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode != 0 or not os.path.isfile(出):
        问题.append(f"★★★ 闸 9 自己挂了（rc={p.returncode}）：{out[-300:]}")
        return
    d = json.load(io.open(出, encoding="utf-8"))
    红 = [h for h in d.get("全命中", []) if h["判"].startswith("🔴")]
    print(f"⑨ 禁词（6.12 的 11 行）：宽口径 {d.get('宽口径', 0)} 行 · 🔴 面向用户 {len(红)}")
    # ★★★★★ 和闸③⑧ 同一个坑：**一处都没捞到 ≠ 干净**，更可能是尺子没咬住（路径/包名错了）。
    if not d.get("宽口径"):
        问题.append("★★★★★ 闸 9：全仓宽口径一行都没捞到 —— ★★★ 这道闸等于没查，"
                    "★ 先看 XING_CARDS/路径对不对（★★ 1115 几次证实：报 0 先怀疑尺子）")
        return
    for h in 红[:12]:
        print(f"   🔴 {h['文件']}:{h['行号']} [{h['形态']}] {h['面向用户理由']}")
        print(f"      {h['原文'][:90]}")
    if 红:
        问题.append(f"★★★★★ 闸 9：{len(红)} 处 6.12 禁词**出现在用户会看到的那一屏** —— "
                    f"★★★ 每条的 ✅ 说法在 json 的「正说法」里；"
                    f"★★ 改措辞不许动判据（规矩 73②：改完重跑闸⑦）")
    if d.get("人核表失配"):
        失 = [e for e in d.get("人核表", []) if e["配上几处"] == 0]
        提醒.append(f"★★★ 闸 9：规矩78 的人核钉死表有 {len(失)} 条配不上了"
                    f"（{'; '.join(e['文件'] + '←' + e['片段'][:18] for e in 失[:3])}）—— "
                    f"★★ 那几处要么被改了措辞、要么被删了，★★★ 归类要重核一遍")
    # ★★★★★ 规矩(78)③：报数的旁边必须写明**这把尺子看不见哪一类**。
    提醒.append("★★ 闸 9 看不见的一类：**裸正文**里对用户说的禁词（不在箱体/面向用户的表格列/"
                "引号交代句/「给用户看的」小节里的散句）—— ★★★ 所以 🔴 0 只能读成"
                "「这四种形态里干净」，★ 不是「全包干净」。")


def 闸10_泄漏全仓():
    """★★★★★ 1116 第十六轮新加（台账 1115 第十五轮 四节② 那一件）——
    ★★★ 补上**泄漏**这一项的文件覆盖：闸④⑤（体检）的泄漏那一格**只喂 39 个 SKILL.md**（覆盖 8%）。

    ★★ 为什么 1115 没扩、1116 扩了：
      ★ 1115 的理由写的是「裸铺报 **60 处**，42 处机器留痕 / 9 处 common_boundaries / 8 处数据清单」。
      ★★★★★ 1116 按规矩(74) 先量 → **那个 60 是错的**（错号 #117）：真数 **370 处 / 489 个 .md**，
        其中 common_boundaries.md 占 **312 处**（8 行 × 39 份拷贝）、机器留痕 **49 处**、数据清单 **5 处**。
      ★★★ 台账把「去重后不同行」（18）和「全仓处数」（370）混在一句话里 —— ★ 正是规矩(80)① 要防的。
      ★★ 真数更大，但**假阳性构成没变**：套上规矩(78)① 那四条「面向用户」判据后 🔴 **0 处**。

    ★★★ 和闸⑨ 同一个写法（**判断只许有一份实现**）：subprocess 调
      `probe/卡改造_1116/量泄漏_1116.py`，★ 本闸只负责把 🔴 变成不打包 + rc=1。
    ★★★ 装之前在现状上量过（规矩74）：🔴 0 处 · 🟡 0 处 · 钉死表 0 条配不上；
      ★★ 五个方向阳性对照全过（箱体 / 面向用户的表格列 / 「给用户看的」小节 / 钉死表改坏 → 🟡 /
        普通内部小节的裸正文 → **故意报不出来**，见下面那条提醒）。
    """
    脚本 = os.path.join(ROOT, "probe", "卡改造_1116", "量泄漏_1116.py")
    if not os.path.isfile(脚本):
        问题.append("★★★ 缺 `probe/卡改造_1116/量泄漏_1116.py` —— ★ 闸 10 无处可查")
        return
    出 = os.path.join(tempfile.gettempdir(), "xing_闸10_泄漏.json")
    env = dict(os.environ, XING_OUT=出)
    p = subprocess.run([sys.executable, "-I", 脚本], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode != 0 or not os.path.isfile(出):
        问题.append(f"★★★ 闸 10 自己挂了（rc={p.returncode}）：{out[-300:]}")
        return
    d = json.load(io.open(出, encoding="utf-8"))
    红 = d.get("🔴面向用户的泄漏", [])
    黄 = d.get("🟡待人判", [])
    分母 = d.get("★分母", {}).get("扫了几个.md", 0)
    print(f"⑩ 泄漏（全仓 {分母} 个 .md）：宽口径 {d.get('★全仓宽口径处数', 0)} 处 · "
          f"🔴 面向用户 {len(红)} · 🟡 待人判 {len(黄)}")
    # ★★★★★ 和闸③⑧⑨ 同一个坑：**一处都没捞到 ≠ 干净**，更可能是尺子没咬住（路径/包名错了）。
    if not d.get("★全仓宽口径处数"):
        问题.append("★★★★★ 闸 10：全仓宽口径一处都没捞到 —— ★★★ 这道闸等于没查，"
                    "★ 先看 XING_CARDS/路径对不对（★★ 1115/1116 几次证实：报 0 先怀疑尺子）")
        return
    if 分母 < 400:
        问题.append(f"★★★★★ 闸 10：只扫到 {分母} 个 .md —— ★★★ 全仓应当是 489 个左右；"
                    f"★ 覆盖掉回去了就等于这道闸白装（错号 #116/#117 就是这么来的）")
    for h in 红[:12]:
        print(f"   🔴 {h['文件']}:{h['行号']} [{h['类']}|{h['形态']}|{h['面向用户']}]")
        print(f"      {h['全文'][:90]}")
    for h in 黄[:6]:
        print(f"   🟡 {h['文件']}:{h['行号']} [{h['类']}|{h['形态']}] {h['全文'][:80]}")
    if 红:
        问题.append(f"★★★★★ 闸 10：{len(红)} 处**内部口吻 / 仓库路径**出现在用户会看到的那一屏 —— "
                    f"★★★ 改措辞不许动判据（规矩 73②：改完重跑闸⑦）")
    if 黄:
        提醒.append(f"★★ 闸 10：{len(黄)} 处**待人判**（词本身有正当产品含义）—— ★ 要人看一眼")
    失 = d.get("🟡钉死表配不上", [])
    if 失:
        提醒.append(f"★★★ 闸 10：规矩79 的人核钉死表有 {len(失)} 条配不上了"
                    f"（{'; '.join(e['文件'] + '←' + e['片段'][:18] for e in 失[:3])}）—— "
                    f"★★ 那几处要么被改了措辞、要么被删了，★★★ 归类要重核一遍")
    # ★★★★★ 规矩(78)③：报数的旁边必须写明**这把尺子看不见哪一类**。
    看 = d.get("★★本尺子看不见的一类", {})
    提醒.append(f"★★ 闸 10 看不见的一类：**裸正文 / 围栏内**的内部口吻（不在箱体/面向用户的表格列/"
                f"引号交代句/「给用户看的」小节里的散句）—— ★ 本轮这一类剩 {看.get('处数', '?')} 处（人核过）；"
                f"★★★ 所以 🔴 0 只能读成「这四种形态里干净」，★ 不是「全包干净」。"
                f"★★★★★ 1116 阳性对照已证实：普通内部小节里新写一句内部口吻，本闸**报不出来**。")


def 闸11_死路径():
    """★★★★★ 1116 第十七轮新加 —— ★ 查「代码里写死了一个**本容器不存在**的仓库路径」。

    ★★ 起因（★ 本轮实测，不是推断）：
      · `probe/判决落卡_1111/判决落卡_1111.py`（★★★ 39 张卡成绩节的**生成器**）→ rc=1，
        FileNotFoundError: `/home/claude/xing-agent-stock_data/手册/93-...md`；
      · `engine/stages.py` 的 `DEFAULT_DATA_ROOT` → `load_daily_json()` 不给 data_root 就 FileNotFoundError。
      ★★ 一扫全仓：**19 处 / 17 个 .py**（★ 本轮已全部改成从 `__file__` 推导，复量 🔴 0）。

    ★★★★★ 为什么要紧（★ 两条都写上，坏消息不许缩短）：
      ① 规矩(80)③「有生成器的字改卡必须同时改生成器」在**成绩节**上执行不了 ——
         ★★ 生成器跑不起来，就既不能重算、也不能拿它验证 49 个 entries 的成绩节有没有被手改
         （★★★ 台账 1116 代价⑫ 那个洞的另一半）。
      ② ★★ 好消息（★ 不许夸大）：这一类**全是响亮地挂**（FileNotFoundError / rc=1），
         ★★★ **不是**「RC=0 但少写一半」那种闷声坏事。

    ★★★ 和闸⑦⑧⑨⑩ 同一个写法（**判断只许有一份实现**）：subprocess 调
      `probe/卡改造_1116/量死路径_1116.py`，★ 本闸只把 🔴 变成不打包 + rc=1。
    ★★ 本闸管的是**仓库自己的脚本能不能跑**，不是卡包内容 —— ★★★ 范围和另外十道不一样，别混着读。
    """
    脚本 = os.path.join(ROOT, "probe", "卡改造_1116", "量死路径_1116.py")
    if not os.path.isfile(脚本):
        问题.append("★★★ 缺 `probe/卡改造_1116/量死路径_1116.py` —— ★ 闸 11 无处可查")
        return
    出 = os.path.join(tempfile.gettempdir(), "xing_闸11_死路径.json")
    env = dict(os.environ, XING_OUT=出)
    env.pop("XING_SCAN_ROOT", None)      # ★★ 阳性对照用的那个口子，闸里不许生效
    p = subprocess.run([sys.executable, "-I", 脚本], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode not in (0, 3) or not os.path.isfile(出):
        问题.append(f"★★★ 闸 11 自己挂了（rc={p.returncode}）：{out[-300:]}")
        return
    d = json.load(io.open(出, encoding="utf-8"))
    红 = d.get("🔴代码在用", [])
    黄 = d.get("🟡只在注释里", [])
    分母 = d.get("★分母", {}).get("扫了.py", 0)
    print(f"⑪ 死路径（扫了 {分母} 个 .py）：🔴 代码在用 {len(红)} · 🟡 只在注释里 {len(黄)}")
    # ★★★★★ 和闸③⑧⑨⑩ 同一个坑：**一个都没扫到 ≠ 干净**。
    if 分母 < 300:
        问题.append(f"★★★★★ 闸 11：只扫到 {分母} 个 .py —— ★★★ 全仓应当是 469 个左右，"
                    f"★ 先看路径对不对（★★ 报 0 先怀疑尺子）")
    for h in 红[:12]:
        print(f"   🔴 {h['文件']}:{h['行']} [{h.get('类', '?')}] {h['原句'][:90]}")
    if 红:
        问题.append(f"★★★★★ 闸 11：{len(红)} 处代码写死了 `/home/claude/xing-agent-stock_data` —— "
                    f"★★★ 这个目录在本容器不存在，跑到那一行就挂；★★ 改成从 `__file__` 推导")
    if 黄:
        提醒.append(f"★★ 闸 11：{len(黄)} 处死路径**只在注释/文档字符串**里（★ 照着粘命令会失败，"
                    f"代码本身没在用）—— ★★ 不拦，但哪天有人照着粘就会踩")
    提醒.append("★★ 闸 11 看不见的一类：**拼出来**的路径（`os.path.join('/home/claude', 'xing-agent-'+x)`）"
                "· 别的写死路径 —— ★★★ 1116 阳性对照已证实：拼接那种**报不出来**；"
                "★ 并且它只保证「不是这一个路径把脚本挡住」，**不保证脚本跑得通**。")


def 闸12_卡里的数():
    """★★★★★ 1121 第二十四轮新加 —— ★ 查「那几个写进卡的标普数，在 `skills_v2/` 全树一共出现几次」。

    ★★★ 为什么（规矩(84) 的配套，★ 同一天连摔两次都是**闸只盯一份文件**）：
      ① 《346》：五个错数「已跟进 42 张卡」—— ★ 新卡自动继承，闸③ 只查 md5 一致，查不出继承；
      ② 《348》：「改一份、铺 42 份就干净」—— ★★ 42×2=84 处，真分母 **133 处**，
         ★★★ 剩下 49 处在 49 份 `references/entries/*.md` 抄着逐字相同的一句。
    🔴 ★★★★★ 所以本闸量的是**全树处数**，不是一份文件的 md5：
      ① 旧值（`14.55` · `-34.1%` · `2.0 年` · `-0.38%` · `0.36%`）全树必须 **0 处**；
      ② 共用文件份数 == 卡数、md5 唯一、**每份都带齐五个新值**；
      ③ 写了 `-33.7%` 或 `1.94 年` 的文件，两个**必须同时在**（🔴 不许只改一半）。
    ★★ 阳性对照（1121 当轮做的，★ 都在副本上种、真仓库一字节没动）：
      · 种回一个 `-34.1%` → 报「旧值还剩 1 处」+「md5 分叉 2 种」，rc=3 ✅
      · 把一份条目的 `1.94 年` 改成 `1.9 年`（**不留任何旧值**）→ 报「只写了两个里的一个」，rc=3 ✅
    ★★★ 和闸⑦⑧⑨⑩⑪ 同一个写法（**判断只许有一份实现**）：subprocess 调
      `probe/卡改造_1116/量卡里的数_1121.py`，★ 本闸只把 🔴 变成不打包 + rc=1。
    ★★★★★ 本闸看不见的一类：**别的写法说同一件事**（「三成三」「约 34%」）—— ★ 一个都报不出来，
      ★★★ 所以 🔴 0 只能读成「这五个字面串干净」，🔴 不是「卡里没有错数」。
    """
    脚本 = os.path.join(ROOT, "probe", "卡改造_1116", "量卡里的数_1121.py")
    if not os.path.isfile(脚本):
        问题.append("★★★ 缺 `probe/卡改造_1116/量卡里的数_1121.py` —— ★ 闸 12 无处可查")
        return
    出 = os.path.join(tempfile.gettempdir(), "xing_闸12_卡里的数.json")
    env = dict(os.environ, XING_OUT=出)
    env.pop("XING_SCAN_ROOT", None)      # ★★ 阳性对照用的那个口子，闸里不许生效
    p = subprocess.run([sys.executable, "-I", 脚本], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode not in (0, 3) or not os.path.isfile(出):
        问题.append(f"★★★ 闸 12 自己挂了（rc={p.returncode}）：{out[-300:]}")
        return
    d = json.load(io.open(出, encoding="utf-8"))
    红 = d.get("🔴", [])
    print(f"⑫ 卡里的数 {'🔴' if 红 else '✅'} 扫 {d.get('★扫了几个文本文件', '?')} 个文本文件 · "
          f"共用 {d.get('★common_boundaries.md 份数', '?')} 份 / "
          f"{d.get('★md5 种数', '?')} 种 md5 · 旧值残留 "
          f"{sum(v.get('合计处', 0) for v in d.get('🔴旧值残留', {}).values())} 处")
    for x in 红:
        问题.append(x)
    for x in d.get("🟡", []):
        提醒.append(x)


def 闸13_指纹对说明书():
    """★★★★★ 1122 第三十二轮新加（**Lin 11-22 09:3x 点头装**）—— 查「给测试组的说明书里写的那串内容指纹
       == 现在 `skills_v2/` 卡的内容指纹」。

    ★★★★★ 为什么装（★ 这条已连着**八轮**刻意没装，1122 当天的事把它推过线）：
      · 1122 半小时里卡的内容指纹换了**三个**（`1a5928f5…` → `0d40c9c3…` → `7d808711…`，09:23 和 09:26 两次落卡），
        ★★★ 而十二道闸**一道都没报** —— 全靠主路每轮人工量一次（规矩(89)）。
      · 连着三轮（《370》/ 第三十 / 第三十一轮）的「包和卡对不上」也是人工发现、人工改对的。
      🔴 ★★★ 这正是规矩(89) 那句话的原型：**闸没报 ≠ 没事**。
    ★★ 本闸只干一件事：把说明书里那串数，和**现在树上**的卡算出来的数比一下。
    ★★★ 和闸⑦⑧⑨⑩⑪⑫ 同一个写法（**判断只许有一份实现**）：subprocess 调
      `probe/出包_1113/量卡内容指纹_1121.py`，用它的 `XING_EXPECT_FP` + rc 0/3，★ 本闸只把 🔴 变成不打包 + rc=1。
    🔴 ★★★★★ 本闸看不见的几类（不许缩短）：
      ① **不说包里的内容是对的** —— 和那把尺子自己印的那句一样（卡里写错的数一样算得出干净指纹）；
      ② **不查 zip** —— 说明书里的 zip SHA-256 带 mtime，换容器重打包就变（第二十五轮阳性对照），本闸一律不碰；
      ③ **不知道「该以谁为准」** —— 对不上只说「两边不一样」，🔴 是该重切包还是该改说明书，**要 Lin 定**（规矩⑱：不许自己顺手切）。
    ★ 逃生门：`XING_ALLOW_FP_DRIFT=1` → 降成 🟡 不拦包（★★ 用它的那一轮必须在《92》里写明为什么）。
    ★ 说明书默认 `手册/349-*.md`，换版本用 `XING_FP_DOC=<路径>`。
    """
    候选 = sorted(glob.glob(os.path.join(ROOT, "手册", "349-*.md")))
    路 = os.environ.get("XING_FP_DOC") or (候选[0] if 候选 else "")
    if not 路 or not os.path.isfile(路):
        提醒.append("★★★ 闸 13：找不到给测试组的说明书（默认 `手册/349-*.md`，或给 XING_FP_DOC）"
                    " —— ★ 这道闸等于没查")
        print("⑬ 指纹对说明书 🟡 找不到说明书 → 没查")
        return
    文 = io.open(路, encoding="utf-8").read()
    写的 = ""
    for 行 in 文.splitlines():
        if "内容总指纹" in 行:
            m = re.search(r"[0-9a-f]{64}", 行)
            if m:
                写的 = m.group(0)
                break
    名 = os.path.basename(路)
    if not 写的:
        提醒.append(f"★★★ 闸 13：《{名[:3]}》里没有「内容总指纹 + 64 位」那一行 —— ★ 这道闸等于没查；"
                    "★★ 规矩(89) 要求说明书把指纹写出来")
        print(f"⑬ 指纹对说明书 🟡 {名[:3]} 里没写指纹 → 没查")
        return
    脚本 = os.path.join(ROOT, "probe", "出包_1113", "量卡内容指纹_1121.py")
    if not os.path.isfile(脚本):
        问题.append("★★★ 缺 `probe/出包_1113/量卡内容指纹_1121.py` —— ★ 闸 13 无处可查")
        return
    env = dict(os.environ, XING_EXPECT_FP=写的)
    env.pop("XING_SCAN_ROOT", None)      # ★★ 阳性对照用的那个口子，闸里不许生效
    p = subprocess.run([sys.executable, "-I", 脚本], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode not in (0, 3):
        问题.append(f"★★★ 闸 13 自己挂了（rc={p.returncode}）：{out[-300:]}")
        return
    现在 = ""
    m = re.search(r"内容总指纹 SHA-256 = ([0-9a-f]{64})", out)
    if m:
        现在 = m.group(1)
    一致 = (p.returncode == 0)
    print(f"⑬ 指纹对说明书 {'✅' if 一致 else '🔴'} {名[:3]} 写的 {写的[:8]}… · "
          f"现在树上 {(现在 or '?')[:8]}…")
    if not 一致:
        句 = (f"★★★★★ 闸 13：**包和说明书对不上** —— 《{名[:3]}》写的 `{写的[:8]}…`，"
              f"现在 `skills_v2/` 算出来是 `{(现在 or '?')[:8]}…` "
              f"→ ★★★ 测试组手里那个包，和现在树上的卡**不是一回事**。"
              f"★★ 当轮必须：① 查差在哪（`git diff <说明书对应的 commit> HEAD -- skills_v2/`）、"
              f"② 记进《92》、③ 推送带给 Lin；"
              f"🔴 **是重切包还是改说明书要 Lin 定**（规矩⑱：不许自己顺手切）。"
              f"★ 逃生门 XING_ALLOW_FP_DRIFT=1。")
        if os.environ.get("XING_ALLOW_FP_DRIFT"):
            提醒.append(句 + "　★★ 本轮用了逃生门 → 降成 🟡 不拦包")
        else:
            问题.append(句)
    if not re.search(r"(commit|入库)[^\n]{0,40}`?[0-9a-f]{7,40}`?", 文, re.I):
        提醒.append(f"★★★ 闸 13：《{名[:3]}》写了指纹、但**没写它对应的 commit** —— "
                    f"★★ 规矩(89) 配套①要求一起写，★★★ 不写就做不了阳性对照"
                    f"（分不清「那个数旧了」和「那个数本身写错」）")
    提醒.append("★★ 闸 13 看不见的三类：① **不说包里的内容是对的**（尺子自己印着这句）；"
                "② **不查 zip**（zip SHA 带 mtime，换容器重打包就变）；"
                "③ **不知道该以谁为准** —— 对不上只说「两边不一样」。")

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
    print("★★★★★ 出包前机器检查（规矩 71 ② · 十三道闸）")
    print("=" * 60)
    head = 闸1_git()
    卡, 文件 = 闸2_数数()
    闸3_共用边界(卡)
    闸4_5_体检(head)
    闸6_待合入项()
    闸7_自述行号()
    闸8_保留词()
    闸9_禁词()
    闸10_泄漏全仓()
    闸11_死路径()
    闸12_卡里的数()
    闸13_指纹对说明书()
    print("-" * 60)
    for x in 提醒:
        print("🟡", x)
    if 问题:
        print(f"\n🔴 **{len(问题)} 道闸没过 → 不打包**")
        for x in 问题:
            print("  ·", x)
        return 1
    print("\n✅ 十三道闸全过")
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
