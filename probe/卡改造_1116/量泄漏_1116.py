# -*- coding: utf-8 -*-
"""★★★★★ 泄漏（内部口吻 / 仓库路径 / 开发痕迹）做成**全仓**格子 —— 台账 1115 第十五轮 四节② 那一件。

★★★ 为什么要这份：体检（闸④⑤）的泄漏这一项**只喂 39 个 SKILL.md**（覆盖 8%）。
   ★ 1115 第十五轮已证实「只看 SKILL.md」在**判据**那一项漏了 124 处（错号 #116），
   ★★★ 泄漏这一项当时**量过、故意没扩**，理由写的是「裸铺报 60 处，七成假阳性」。
★★★★★ 本轮按规矩(74) 先量 → **那个 60 是错的**（错号 #117）：真数见下，台账把
   「去重后不同行」和「全仓处数」两个口径混在一句话里了（★★ 正是规矩(80)① 要防的）。

★★ 分工（★★★ 判断只许有一份实现 —— 和闸⑦⑧⑨ 同一个写法）：
   · 本份 = 泄漏的**全仓**尺子（489 个 .md）→ 装成**闸⑩**。
   · `体检_1109.py` 的泄漏那一格仍是**窄口径（只 SKILL.md）**，★★★ 报头已标明，不许再说它是全仓。

★★★ 判据照抄规矩(78)①「哪几种形态算说给用户的」（★ 引号只是其中一种）：
   ① 小节标题写着「给用户看的 / 用户看到 / 对用户说」→ 这一节整节算
   ② 箱体画线（│┌└├）里的输出样例
   ③ 表格单元格，且**该列列头**是面向用户的那一列（表头本身也算）
   ④ 引号，且**同一行**在交代要怎么说
   ★★ 一律先剔：frontmatter · 带否定的那一行（它在说禁令本身）· 成绩节自动生成那一行（有生成器）。

★★★★★ 规矩(78)③ —— **本尺子看不见哪一类**（必须跟着数一起报）：
   🔴 **裸正文**里的内部口吻（不在箱体 / 面向用户的表格列 / 引号 / 「给用户看的」小节里的散句）。
   ★★ 本轮实测裸正文命中 N 行，人核后面向用户 0 行；★★★ 但那是**人核的结论，不是尺子的能力**。
"""
from __future__ import annotations
import os, re, json, sys, collections

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
包 = os.path.join(ROOT, os.environ.get("XING_CARDS", "skills_v2"))
读 = lambda p: open(p, encoding="utf-8", errors="replace").read()

# ★★ 两档：确定（出现就是泄漏）· 待判（词本身有正当产品含义）—— ★ 照抄体检那份，口径不许偷偷改
泄漏_确定 = [
    (re.compile(r"（?★+\s*(我|Claude|主路|B 路|账本|规矩\s*[㊀-㊿\d])"), "内部口吻/账本"),
    (re.compile(r"(probe/|跑前登记|待配对检验|OOM|git |commit )"), "仓库路径/开发痕迹"),
]
泄漏_待判 = [
    (re.compile(r"作废(?=[^。\n]{0,20}(跑批|口径|登记|版本|记录))"
                r"|(?:跑批|口径|登记)[^。\n]{0,20}作废"), "「作废」挨着开发语境"),
    (re.compile(r"\b(TODO|FIXME|XXX|待补|占位)\b"), "占位词"),
]

否定 = re.compile(r"不许|不输出|不得|不要|不能|别说|别用|永远不用|永远不许|❌|红线|禁用|不该|不说|不写|不暴露|不把|绝不|勿|改掉|换成|已撤回|无效")
用户小节 = re.compile(r"给用户看的|用户看到|对用户说|给用户的")
用户列 = re.compile(r"要这么说|怎么答|对用户说|说什么|对用户|✅|为什么答不了|怎么说|用户看到|给用户")
交代句 = re.compile(r"结论写|状态为|要写明|必须说|答用户|对用户说|说成|写明|回答|输出.{0,4}[「『]")
成绩标记 = "XING-成绩-自动生成"

def 单元格(l):
    return [c.strip() for c in l.strip().strip("|").split("|")]

# ★★★★★ 人核钉死表（规矩79③：人核结论必须钉进脚本，不是写在报告里）
#   ★★ 规矩(79) 那条：**钉死表自己会烂** → 下面 `钉死表自查` 会把配不上的报成 🟡。
人核放过 = [
    # ---- common_boundaries.md：6.12/6.17 那张共用边界本体，★ 是给 AI 读的内部工程规格，不是给用户的屏
    ("references/shared/common_boundaries.md", "原文 grep 得到", "6.9 出处五档的内部定义（★ 讲的是我们怎么分档）"),
    ("references/shared/common_boundaries.md", "他只会当成一个意见", "「智慧」的内部定义段"),
    ("references/shared/common_boundaries.md", "我们有「**不许下结论**」", "6.17 内部论证：为什么要配反方"),
    ("references/shared/common_boundaries.md", "融合 V1 之后新增三节", "版本记录表（内部变更史）"),
    ("references/shared/common_boundaries.md", "曾用这个办法算出", "★★★★★ 小节标题带「给用户的」但这句是**撤回记录**的内部引注（判据①的假阳性，见下）"),
    ("references/shared/common_boundaries.md", "写成「（欧奈尔）」", "内部订正记录（叫法改过）"),
    ("references/shared/common_boundaries.md", "我们自己数的：翻转", "环境闸四道关的内部实测注"),
    ("references/shared/common_boundaries.md", "这个 25 怎么来的", "机会集宽基 25 这个数的内部来历"),
    # ---- 数据清单.md：内部「有没有这份数据」对照表，★ 出处列写的就是仓库路径
    ("references/数据清单.md", "pool_FULL_ALL", "内部数据清单的**出处列**（路径就是答案本身）"),
    ("references/数据清单.md", "fundamental_buildout_1030", "同上"),
    ("references/数据清单.md", "sec_earnings_dates_1030", "同上"),
    ("references/数据清单.md", "pit_universe_symbols", "同上"),
    # ---- entries：给 AI 的答法交代
    ("references/entries/技-1.md", "我们留空是**照原文**", "给 AI 的答法交代（★ 紧跟着就是「不许答…」）"),
    # ---- ★★★ 1116 人核：那 49 处机器留痕（有生成器 → 规矩80③ 那一类）
    (".md", "本节由 `probe/判决落卡_1111/判决落卡_1111.py`",
     "★★ 成绩节的出处引注，由 `判决落卡_1111.py` 自动生成（49 个 entries 文件同一行）—— "
     "★★★ 内部留痕，不是对用户说的话；★ 要改得连生成器一起改（规矩80③）"),
    # ---- ★★★ 1116 人核：示例输出里的匿名代码
    ("xing-screener/SKILL.md", "XXX",
     "★★ 箱体示例输出里拿 `XXX` 当**匿名股票代码**（不是 TODO/占位）—— ★ 体检那份的注释早写明「示例里的匿名代码不算」"),
]
def 被人核放过(h):
    for f, frag, why in 人核放过:
        if h["文件"].endswith(f) and frag in h["全文"]:
            return why
    return None

def 钉死表自查(全命中):
    失 = []
    for f, frag, why in 人核放过:
        if not any(h["文件"].endswith(f) and frag in h["全文"] for h in 全命中):
            失.append({"文件": f, "片段": frag, "理由": why,
                       "★": "★★★ 配不上了 —— ★ 要么那行改过了，要么尺子口径变了，**当没核过**"})
    return 失

def 量() -> dict:
    卡 = sorted(d for d in os.listdir(包)
                if os.path.isdir(os.path.join(包, d))
                and os.path.exists(os.path.join(包, d, "SKILL.md")))
    文件数 = 0
    全命中 = []
    for c in 卡:
        根 = os.path.join(包, c)
        文件 = []
        for dp, _d, fns in os.walk(根):
            for fn in sorted(fns):
                if fn.endswith(".md"):
                    文件.append(os.path.join(dp, fn))
        文件.sort(key=lambda p: (0 if os.path.basename(p) == "SKILL.md" and os.path.dirname(p) == 根 else 1, p))
        for p in 文件:
            文件数 += 1
            rel = os.path.relpath(p, 包)
            行s = 读(p).splitlines()
            在fm = False; 在围栏 = False; 小节 = ""; 表头 = None
            for i, 行 in enumerate(行s):
                s = 行.strip()
                if i == 0 and s == "---":
                    在fm = True; continue
                if 在fm:
                    if s == "---": 在fm = False
                    continue
                if s.startswith("```"):
                    在围栏 = not 在围栏; continue
                if s.startswith("#"):
                    小节 = s; 表头 = None
                if s.startswith("|"):
                    if re.match(r"^\|[\s:\-|]+\|?$", s):
                        表头 = 单元格(行s[i-1]) if i else None
                        continue
                else:
                    表头 = None
                if 成绩标记 in 行:
                    continue
                for 档, 组 in (("确定", 泄漏_确定), ("待判", 泄漏_待判)):
                    for 正则, 名 in 组:
                        m = 正则.search(行)
                        if not m:
                            continue
                        # ---- 形态（判据照抄规矩78①）----
                        if s.startswith("|"):
                            形态 = "表格单元格"
                        elif s.startswith(("│", "┌", "└", "├", "┤", "┬", "┴")):
                            形态 = "箱体画线"
                        elif re.search(r"[「『“\"][^「」『』“”\"]*" + re.escape(m.group(0)[:6]), 行):
                            形态 = "引号"
                        elif 在围栏:
                            形态 = "围栏内"
                        else:
                            形态 = "裸正文"
                        # ---- 面向用户？----
                        面向 = None
                        if 用户小节.search(小节):
                            面向 = "①「给用户看的」小节整节"
                        elif 形态 == "箱体画线":
                            面向 = "②箱体输出样例"
                        elif 形态 == "表格单元格" and 表头:
                            格 = 单元格(行)
                            for j, g in enumerate(格):
                                if m.group(0)[:6] in g and j < len(表头) and 用户列.search(表头[j]):
                                    面向 = f"③表格面向用户的列（列头：{表头[j][:20]}）"; break
                            if 面向 is None and any(用户列.search(h or "") for h in 表头) and 用户列.search(" ".join(格[:1])):
                                面向 = "③表头本身"
                        elif 形态 == "引号" and 交代句.search(行):
                            面向 = "④引号 + 同行在交代怎么说"
                        h = {"卡": c, "文件": rel, "行号": i + 1, "档": 档, "类": 名,
                             "形态": 形态, "小节": 小节[:60], "面向用户": 面向,
                             "带否定": bool(否定.search(行)), "全文": s[:220]}
                        全命中.append(h)
    # ---- 定红黄 ----
    红, 黄, 放过 = [], [], []
    for h in 全命中:
        why = 被人核放过(h)
        if why:
            h["人核放过"] = why; 放过.append(h); continue
        if h["带否定"]:
            continue                       # ★ 它在说禁令本身
        if h["面向用户"] is None:
            continue                       # ★★★ 尺子看不见的那一类（裸正文/围栏）→ 下面单独报
        (红 if h["档"] == "确定" else 黄).append(h)
    裸 = [h for h in 全命中 if h["面向用户"] is None and not h["带否定"] and not 被人核放过(h)]
    报 = {
        "★分母": {"卡数": len(卡), "扫了几个.md": 文件数,
                 "★★★": "★ 报「全仓 N 处」先报这个（规矩80①）"},
        "★全仓宽口径处数": len(全命中),
        "★去重后不同行": len({(h["类"], h["全文"]) for h in 全命中}),
        "🔴面向用户的泄漏": 红,
        "🟡待人判": 黄,
        "★人核放过": [{"文件": h["文件"], "行号": h["行号"], "理由": h["人核放过"], "全文": h["全文"][:90]} for h in 放过],
        "🟡钉死表配不上": 钉死表自查(全命中),
        "★★本尺子看不见的一类": {
            "形态": "裸正文 / 围栏内（规矩78③）",
            "处数": len(裸),
            "★★★": "★ 这里的 0 是**人核的结论，不是尺子的能力** —— ★★ 裸正文新写一句内部口吻，本闸报不出来",
            "按文件": dict(collections.Counter(h["文件"] for h in 裸).most_common(10)),
            "逐条": [{"文件": h["文件"], "行号": h["行号"], "类": h["类"], "形态": h["形态"], "全文": h["全文"][:160]} for h in 裸],
        },
        "★按形态": dict(collections.Counter(h["形态"] for h in 全命中)),
        "★按文件 top": dict(collections.Counter(h["文件"] for h in 全命中).most_common(6)),
    }
    return 报

def main() -> int:
    报 = 量()
    出 = os.environ.get("XING_OUT") or os.path.join(ROOT, "手册", "量泄漏_1116.json")
    json.dump(报, open(出, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    d = 报["★分母"]
    print(f"★ 分母：{d['卡数']} 张卡 · **{d['扫了几个.md']} 个 .md**（规矩80①）")
    print(f"★ 全仓宽口径 {报['★全仓宽口径处数']} 处 · 去重后不同行 {报['★去重后不同行']} 行")
    print(f"★ 人核放过 {len(报['★人核放过'])} 处 · 🟡钉死表配不上 {len(报['🟡钉死表配不上'])} 条")
    看不见 = 报["★★本尺子看不见的一类"]
    print(f"★★★ 看不见的一类（裸正文/围栏）：{看不见['处数']} 处 —— {看不见['★★★']}")
    print(f"🔴 面向用户的泄漏：**{len(报['🔴面向用户的泄漏'])} 处** · 🟡 待人判：{len(报['🟡待人判'])} 处")
    for h in 报["🔴面向用户的泄漏"][:20]:
        print(f"  🔴 {h['文件']}:{h['行号']} [{h['类']}|{h['形态']}|{h['面向用户']}]")
        print(f"      {h['全文'][:150]}")
    for h in 报["🟡待人判"][:10]:
        print(f"  🟡 {h['文件']}:{h['行号']} [{h['类']}|{h['形态']}] {h['全文'][:110]}")
    for x in 报["🟡钉死表配不上"]:
        print(f"  🟡钉死表 {x['文件']} / 「{x['片段']}」—— {x['★']}")
    print(f"→ {出}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
