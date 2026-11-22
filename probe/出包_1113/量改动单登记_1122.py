# -*- coding: utf-8 -*-
"""
量「`手册/给主chat-*` 这些单子有没有被登记 / 有没有撞号」—— 只读 · rc 0/3
★★★★★ 为什么要这把尺子（1122 第三十二轮当天暴露的缺口）：
   ★★★ 《待合入项清单》的覆盖面是「各组报告里写过的改动」，**全靠人看到了往里写**。
   ★ 1122 早上三份 `给主chat-…改动单` 落在 **main 上**，闸⑥ 照样报「未合入 0 条」
   —— ★★ 是主路当轮人工登的；★★★★★ 没人登的那天，它就是 V2.4.4 那次「四张卡的改动在正式包里全丢了」。
★★ 本尺子查三件：
   ① **改动单没登记**：`给主chat-*改动单v0.X-*.md` 的 (卡, 版本) 在《待合入项清单》里找不到 → 🔴
   ② **撞号**：同一张卡的同一个版本号挂着**两份内容不同**的单子 → 🔴（★ 1121 有过先例：两份内容不同的卡都叫 v0.17）
   ③ **测试单没登记**：`给主chat-*测试单-*.md` 找不到 → 🟡（★ 测试单不改卡，不该拦包）
🔴 看不见的几类（不许缩短）：
   · **只认文件名里的 (卡, 版本)** —— ★ 单子正文里写了别的版本号，它读不出来；
   · **不判单子的内容对不对**，也不判「该不该合」—— ★★ 只说「清单里有没有这一条」；
   · **只扫 `手册/给主chat-*`** —— ★★★ 别的 chat 开分支放的单子、换了命名的单子，一个都扫不到
     （★ 这正是台账里「清单管不住别的 chat 开分支放的拍板单」那条，本尺子**没解决它**）。
用法：
   python3 probe/出包_1113/量改动单登记_1122.py              # 只打印
   XING_OUT=<路径> python3 ...                               # 另存 JSON（闸⑭ 用这个口）
"""
import glob, hashlib, io, json, os, re, subprocess, sys

ROOT = os.environ.get("XING_SCAN_ROOT", "/home/claude/stock_data")
手册 = os.path.join(ROOT, "手册")
清单路 = os.path.join(手册, "待合入项清单.md")

卡名映射 = {"技术面": "xing-ta-master", "基本面": "xing-fa-master"}


def 解文件名(名):
    """从文件名取 (类型, 卡, 版本, 题)。★ 取不出版本的返回 版本=None。"""
    m = re.match(r"给主chat-(?:(.*?)-)?(改动单|测试单)\s*(v[\d.]+)?-(.*?)-(\d{4})\.md$", 名)
    if not m:
        return None
    卡段, 类型, 版本, 题, 日 = m.groups()
    卡段 = 卡段 or ""
    卡 = next((k for k in 卡名映射 if k in 卡段), 卡段 or "没写卡")
    return {"类型": 类型, "卡": 卡, "版本": 版本, "题": 题, "日": 日, "文件": 名}


def 卡的沿革(卡):
    """卡顶部那一行的「vX.Y = 这一版干了什么」拆成 {版本: 描述}。
    ★★★★★ 为什么要读描述、不能只比号：1122 当天连踩两次 ——
      ① 卡头从 v0.20 跳到 v0.21，「比卡头旧就算已落」把一份**根本没进卡**的 v0.20 静静放过；
      ② 卡头的 v0.20 写的是「做空仓位分品种」，而同号那份单子讲的是「目标区合成 / 波浪两条」
         —— 🔴 **号一样、事两样**。
    ★★ 所以判「落过没有」要看**描述里有没有这份单子讲的那件事**。
    """
    目录 = 卡名映射.get(卡)
    if not 目录:
        return {}
    p = os.path.join(ROOT, "skills_v2", 目录, "SKILL.md")
    if not os.path.isfile(p):
        return {}
    头 = "\n".join(io.open(p, encoding="utf-8").read().splitlines()[:40])
    return {m.group(1): m.group(2) for m in re.finditer(r"(v[\d.]+)\s*=\s*([^；;]{0,160})", 头)}


def 题对得上(题, 描述):
    """★ 把单子标题切成 3 字一段，有一段出现在卡的那句描述里就算对得上。
    🔴 看不见的一类：同一件事**换一套词**写（和规矩(90) 那条同一个病）。"""
    清 = lambda t: re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    a, b = 清(题), 清(描述)
    return any(a[i:i + 3] in b for i in range(max(len(a) - 2, 0)))


def 卡里有过的版本(卡):
    """卡顶部那一行会写「v0.20 = … ；v0.19 = … ；v0.18 = …」的沿革。
    ★★★★★ 为什么要读它：1122 当天踩过一次**假阴性** —— 卡头从 v0.20 跳到 v0.21，
      于是「比卡头旧就算已落」这条把一份**根本没进卡**的 `改动单 v0.20` 静静放过了。
    🔴 所以「比卡头旧」不够，还得卡自己的沿革里**点过这个号的名**。
    """
    目录 = 卡名映射.get(卡)
    if not 目录:
        return None
    p = os.path.join(ROOT, "skills_v2", 目录, "SKILL.md")
    if not os.path.isfile(p):
        return None
    头 = "\n".join(io.open(p, encoding="utf-8").read().splitlines()[:40])
    return set(re.findall(r"(v[\d.]+)\s*[=（(]", 头))


def 卡头版本(卡):
    """读卡顶部的版本行，★ 只用来和单子的版本号并排显示，🔴 不做判断依据。"""
    目录 = 卡名映射.get(卡)
    if not 目录:
        return None
    p = os.path.join(ROOT, "skills_v2", 目录, "SKILL.md")
    if not os.path.isfile(p):
        return None
    for 行 in io.open(p, encoding="utf-8").read().splitlines()[:40]:
        m = re.search(r"\*\*(v[\d.]+)\s*[（(]", 行)
        if m:
            return m.group(1)
    return None


def 版本元(v):
    """`v0.18` → (0, 18)。★★ 这样 v0.2 < v0.20、v0.1 < v0.15 都排得对（🔴 字符串比就排错）。"""
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return None


def main():
    if not os.path.isfile(清单路):
        print("★★★ 找不到《待合入项清单》→ 这把尺子无处可查")
        sys.exit(3)
    清单 = io.open(清单路, encoding="utf-8").read()
    # ★★ 清单里把空格写法统一掉再找（「改动单 v0.18」/「改动单v0.18」两种都有）
    清单平 = re.sub(r"\s+", "", 清单)

    单子, 坏名 = [], []
    for p in sorted(glob.glob(os.path.join(手册, "给主chat-*.md"))):
        d = 解文件名(os.path.basename(p))
        if d is None:
            坏名.append(os.path.basename(p))
            continue
        d["md5"] = hashlib.md5(io.open(p, "rb").read()).hexdigest()
        单子.append(d)

    红, 黄 = [], []

    # ① / ③ 登记 —— ★★★★★ 判断只有一句话：**版本号比卡头新、又不在清单里**才是 🔴
    #   ★★ 为什么要比卡头：v0.4~v0.16 那些老单子早就落进卡了，清单里当然没有（清单只管「还没合的」）。
    #   🔴 第一版尺子漏了这一步，当场报了 9 张假红牌 —— ★★★ 这类「闸乱叫」会被人绕，比不装还坏。
    未登记改动单, 未登记测试单, 等人看 = [], [], []
    for d in 单子:
        if not d["版本"]:
            # ★★ 没版本号的（测试单多半这样）→ 退一步用「题」里的头一截去清单里找
            头 = re.sub(r"[^\w\u4e00-\u9fff]", "", d["题"])[:4]
            if 头 and 头 in re.sub(r"[^\w\u4e00-\u9fff]", "", 清单):
                continue                  # ✅ 清单里提到了
            黄.append(f"★★ 《{d['文件']}》**没版本号、清单里也找不到**（按「{头}」找的，★ 只取前 4 个字）—— "
                      f"★ {d['类型']}不改卡、不拦包，★★ 但不登记就会忘了跑；"
                      f"★★★ 单子名里带上 vX.Y 本尺子才认得出。")
            continue
        卡头 = 卡头版本(d["卡"])
        v, h = 版本元(d["版本"]), 版本元(卡头 or "")
        d["卡头"] = 卡头
        有版本 = d["版本"] in 清单平
        有卡 = (d["卡"] in 清单) if d["卡"] in 卡名映射 else True
        已登记 = 有版本 and 有卡
        沿革 = 卡的沿革(d["卡"])
        底 = min((版本元(x) for x in 沿革 if 版本元(x)), default=None)
        if d["版本"] in 沿革:
            if 题对得上(d["题"], 沿革[d["版本"]]):
                continue                  # ✅ 卡的沿革点了这个号、讲的也是这件事
            if 已登记:
                continue                  # ✅ 清单里挂着 → 有人盯着了（规矩71：格子才管得住）
            等人看.append(d)              # 🟡 号一样、事两样、又没人登记 → 可能根本没进卡
            continue
        if v and 底 and v < 底:
            continue                      # ✅ 比沿革写到的最老那版还旧 → 卡头不写那么远，不判
        if v and h and v <= h and not 已登记:
            等人看.append(d)              # 🟡 不比卡头新、沿革里又没点名 → 要人看一眼
            continue
        if 已登记:
            continue                      # ✅ 比卡头新，但清单里挂着
        (未登记改动单 if d["类型"] == "改动单" else 未登记测试单).append(d)

    for d in 未登记改动单:
        红.append(f"★★★★★ **改动单没登记、也还没进卡**：《{d['文件']}》"
                  f"（{d['卡']} {d['版本']}，★ 卡头现在 {d.get('卡头') or '?'}）"
                  f"—— ★★★ 规矩71③ 要求看到当场往《待合入项清单》加一行；"
                  f"🔴 ★★ 不登记就是 V2.4.4 那次「四张卡的改动在正式包里全丢了」的入口。")
    for d in 未登记测试单:
        黄.append(f"★★ **测试单没登记**：《{d['文件']}》（{d['卡']} {d['版本']}）不在清单里 —— "
                  f"★ 测试单不改卡、不拦包，★★ 但不登记就会忘了跑。")
    for d in 等人看:
        卡话 = 卡的沿革(d["卡"]).get(d["版本"], "")
        黄.append(f"★★★★★ 《{d['文件']}》**可能根本没进卡** —— "
                  f"★ 它的号是 {d['版本']}，而卡顶部沿革里 {d['版本']} 那一句写的是"
                  f"「{(卡话 or '没点这个号').strip()[:46]}…」，**和这份单子讲的不是一件事**；"
                  f"★★ 清单里也没挂着它。★★★ 查法：拿单子标题里的词去 `skills_v2/` 全树搜一遍，"
                  f"0 处就是真没进（1122 就是这么捞出 v0.19 A 段的）。")

    # ② 撞号
    桶 = {}
    for d in 单子:
        if d["版本"]:
            桶.setdefault((d["卡"], d["类型"], d["版本"]), []).append(d)
    for (卡, 类型, 版本), 组 in sorted(桶.items()):
        if len(组) < 2:
            continue
        if len({x["md5"] for x in 组}) == 1:
            黄.append(f"★★ {卡}大师卡 {类型} **{版本} 有 {len(组)} 份同名文件，内容相同** —— ★ 只是重复，不拦包")
            continue
        # ★★★★★ 逃生口不是环境变量，是**格子**（规矩71：规则管不住，格子才管得住）：
        #   《待合入项清单》里写一行「撞号已判 vX.Y …」说明**落的是哪一份、另一份怎么办**，这张红牌才消。
        #   ★★ 这样能清掉它的只有「把话写下来」，🔴 不是「改个文件名把证据抹掉」。
        if f"撞号已判{版本}" in 清单平:
            黄.append(f"★★ {卡}大师卡 {类型} {版本} 撞号 —— ✅ 《待合入项清单》里已写明落的是哪一份（「撞号已判{版本}」）")
            continue
        句 = (f"★★★★★ **撞号**：{卡}大师卡 {类型} **{版本}** 挂着 **{len(组)} 份内容不同**的单子 —— "
              f"{'　'.join('《' + x['题'] + '》' for x in 组)}。"
              f"★★★ 1121 有过同一个坑（两份内容不同的卡都叫 v0.17）；"
              f"★★ 说「落了 {版本}」时**分不清落的是哪一份**。"
              f"★★★ 要清这张红牌：往《待合入项清单》写一行 `撞号已判 {版本}`，"
              f"写明**落的是哪一份、另一份怎么办** —— 🔴 不许靠改文件名把证据抹掉（规矩⑰：不改别人的文档）。")
        红.append(句)

    # ④ 🆕 远端分支上有、main 没有的单子 —— ★★★ 台账挂了很多轮的那条
    #    「《待合入项清单》管不住别的 chat 开分支放的拍板单」，★ 这一步第一次把它量出来。
    #    🔴 只报 🟡 不拦包：★★ 分支上的东西不是 main 的责任，★★★ 要不要拦**要 Lin 定**（台账 ⑥''）。
    分支漏 = []
    try:
        本地有 = set(subprocess.run(
            ["git", "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only",
             os.environ.get("XING_BRANCH_BASE", "HEAD"), "手册/"],
            cwd=ROOT, stdout=subprocess.PIPE, timeout=60
        ).stdout.decode("utf-8", "replace").split("\n"))
        枝 = [b.strip() for b in subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"],
            cwd=ROOT, stdout=subprocess.PIPE, timeout=60
        ).stdout.decode("utf-8", "replace").split("\n") if b.strip()]
        for b in 枝:
            if b.endswith("/HEAD") or b == "origin/main":
                continue
            名单 = subprocess.run(
                ["git", "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", b, "手册/"],
                cwd=ROOT, stdout=subprocess.PIPE, timeout=60
            ).stdout.decode("utf-8", "replace").split("\n")
            少 = [f for f in 名单 if f and f not in 本地有
                  and re.search(r"(给主chat|改动单|拍板)", f)]
            if 少:
                分支漏.append((b, 少))
    except Exception as e:                                   # ★ 没 git / 超时都不许让尺子挂
        黄.append(f"★★ 分支那一步没跑成（{type(e).__name__}）—— ★ 这一项等于没查")
    for b, 少 in 分支漏:
        黄.append(f"★★★★★ **分支 `{b}` 上有 {len(少)} 份 main 没有的单子** —— "
                  + "　".join("《" + os.path.basename(f).rstrip(".md")[:34] + "》" for f in 少[:4])
                  + (f" …另 {len(少)-4} 份" if len(少) > 4 else "")
                  + "。★★★ 这就是台账那条「清单管不住别的 chat 开分支放的拍板单」；"
                    "🔴 本尺子只说「分支上有」，**没看里面写的是什么、也没判该不该合**。")

    for 名 in 坏名:
        黄.append(f"★★ 《{名}》文件名不合「给主chat-<卡>-(改动单|测试单)[ vX.Y]-<题>-<日期>.md」→ ★ 本尺子跳过了它")

    out = {
        "★扫了几份单子": len(单子),
        "★改动单": sum(1 for d in 单子 if d["类型"] == "改动单"),
        "★测试单": sum(1 for d in 单子 if d["类型"] == "测试单"),
        "🔴": 红,
        "🟡": 黄,
        "★★本尺子看不见的": [
            "只认文件名里的 (卡, 版本)，单子正文里写的版本号读不出来",
            "判「已落进卡」只比版本号大小、不读卡的内容 —— 卡头写 v0.20 不等于落的就是那份 v0.20 单子",
            "不判单子的内容对不对、也不判该不该合 —— 只说清单里有没有这一条",
            "登记那一项只扫 手册/给主chat-*：换了命名的单子扫不到",
            "分支那一项只看文件名有没有 给主chat/改动单/拍板，没读里面写的是什么、也没判该不该合",
        ],
        "★分支上 main 没有的单子": {b: 少 for b, 少 in 分支漏},
        "★★★三秒版": f"🔴 红牌 {len(红)} 张 · 🟡 黄牌 {len(黄)} 张 · ★ 单子 {len(单子)} 份"
                      f" · ★ 分支上另有 {sum(len(x) for _, x in 分支漏)} 份 main 没有的",
    }
    路 = os.environ.get("XING_OUT")
    if 路:
        io.open(路, "w", encoding="utf-8").write(
            json.dumps(out, ensure_ascii=False, indent=1))
    print(out["★★★三秒版"])
    for x in 红:
        print("🔴", x)
    for x in 黄:
        print("🟡", x)
    sys.exit(3 if 红 else 0)


if __name__ == "__main__":
    main()
