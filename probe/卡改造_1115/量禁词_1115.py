# -*- coding: utf-8 -*-
"""★★★★★ 6.12 那张表 **11 行「禁词」** 做成格子（台账 1115 第十三轮 六节② · 规矩(78) 装进闸）。

★★★ 和隔壁那把尺子的分工：
   · `量失效位解释_1115.py` 管 6.12 的**第 12 行**「失效位」—— **保留词**，查「解释在不在旁边」（规矩79 → 闸⑧）。
   · 本份管其余 **11 行**—— **禁词**，查「有没有出现在**用户会看到的那一屏**」（规矩78 → 闸⑨）。

★★★★★ 为什么不能只 grep：1114 那版直接报 **155 处**，**92% 是假的**（错号 #109/#110）——
   6.12 自己写了范围说明：「管**面向用户的输出措辞**，★★★ 不管卡里内部判据的写法」。
   ★★ 全包宽口径捞一遍是 **900 多行**，绝大多数是内部论证箱体 / 路由块 / 版本历史表 / 禁令本身。

★★★ 所以判据按规矩(78)① 写成「**哪几种形态算说给用户的**」（引号只是其中一种）：
   ① 小节标题自己写着「给用户看的 / 用户看到 / 对用户说」→ ★★★★★ 这一节**整节**算
   ② 箱体画线（│┌└├）里的输出样例
   ③ 表格单元格，且**该列列头**是「要这么说 / 怎么答 / 对用户说 / ✅ …」这类面向用户的列（★ 表头本身也算）
   ④ 引号，且**同一行**在交代要怎么说（结论写「…」/ 状态为「…」/ 必须说明「…」）
   ★★ 一律先剔掉：**带否定的那一行**（不许/不输出/❌/红线…→ 它在说禁令本身）· frontmatter ·
      `common_boundaries.md`（★ 6.12 这张表自己就要写这些词）。

★★★★★ 规矩(78)③ —— **这把尺子看不见哪一类**（★ 必须跟着数一起报）：
   🔴 **裸正文**里对用户说的话（不在箱体/表格/引号/「给用户看的」小节里的散句）。
   ★ 本轮实测：裸正文非否定命中 226 行，人核后面向用户 0 行（全是内部论证）——
     ★★★ 但这是**人核的结论，不是尺子的能力**；裸正文新写一句对用户说的禁词，本闸**报不出来**。
"""
from __future__ import annotations
import os, re, json

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
包 = os.path.join(ROOT, os.environ.get("XING_CARDS", "skills_v2"))
读 = lambda p: open(p, encoding="utf-8").read()

# ★★★ 6.12 的 11 行禁词（★ 第 12 行「失效位」是保留词，归闸⑧，不在这儿）
禁词表 = [
    ("分流 / 路由 / 编排",                    ["分流", "路由", "编排"],            "—（用户不该知道有这件事）"),
    ("共用边界 / 措辞红线 / 骨架卡 / 场景卡 / 能力卡",
     ["共用边界", "措辞红线", "骨架卡", "场景卡", "能力卡"],                        "—（同上）"),
    ("出处五档 / 第 ⑤ 档",                    ["出处五档", "第 ⑤ 档", "第⑤档"],     "「这是温斯坦的原话」/「我们自己填的」/「行业通行做法」"),
    ("池子口径 / large_mid / 覆盖率",         ["池子口径", "large_mid", "覆盖率"],   "「这只票我们还没有财务数据」"),
    ("技术面第六层",                          ["第六层"],                           "「什么情况算这套做法走坏了」"),
    ("前提成立 / 已激活",                     ["前提成立", "已激活"],                "「现在的条件够不够」"),
    ("回测 / 样本外",                         ["回测", "样本外"],                    "「拿过去的数据试过」/「用一段它没见过的时间试过」"),
    ("最大回撤",                              ["最大回撤"],                          "「从最高点往下亏掉的那一段」"),
    ("水下时间",                              ["水下时间"],                          "「我账户里的数多久没超过之前的最高点」"),
    ("系统判定",                              ["系统判定"],                          "必须说是谁的方法（永远不许用）"),
    ("市场温度 ×× 分 / 健康度 ×× 分",         ["市场温度", "健康度"],                "不许出现（撞 6.2 不做综合评分）"),
]

否定 = re.compile(r"不许|不输出|不得|不要|不能|别说|别用|永远不用|永远不许|❌|红线|禁用|不该|不说|不写|不暴露|不把|绝不|勿|改掉|换成")
用户小节 = re.compile(r"给用户看的|用户看到|对用户说|给用户的")
用户列 = re.compile(r"要这么说|怎么答|对用户说|说什么|对用户|✅|为什么答不了|怎么说|用户看到|给用户")
交代句 = re.compile(r"结论写|状态为|要写明|必须说|答用户|对用户说|说成|写明|回答|输出.{0,4}[「『]")

def 单元格(l):
    return [c.strip() for c in l.strip().strip("|").split("|")]

# ★★★★★ 人核钉死表（照抄《197》四节那 8 类「刻意不改」+ 本轮新核的）
# ★★ 规矩(79) 第三句：人核结论必须钉进脚本。★★★ 规矩(79) 新增那一条：**钉死表自己会烂** →
#   下面 `钉死表自查` 会报出配不上的条目（🟡），★ 免得某一条悄悄从「已核过」变成「面向用户」。
人核放过 = [
    ("xing-main/SKILL.md", "否则回测买得到", "内部工程说明：主语是下单那一刻的成交额门槛（《197》四①，★ Lin 未核：D-⑲）"),
    ("xing-screener/SKILL.md", "否则回测买得到", "同上（《197》四①）"),
    ("xing-main/SKILL.md", "系统判定", "反面例子：「而我们写『系统判定』，他用一年也学不到」（《197》四②）"),
    ("xing-skill-builder/SKILL.md", "回测健康度 85 分", "❌「不能这么说」那一列（《197》四④）"),
    ("xing-main/SKILL.md", "large_mid", "内部口径说明格，格里自己写着「对用户说的只数是 2,000」（《197》四⑧）"),
    ("xing-main/SKILL.md", "成交额前 500", "同一格的实测列（《197》四⑧）"),
    ("xing-main/SKILL.md", "技术面大师能力卡", "路由/分流表（《197》四⑥）"),
    ("xing-main/SKILL.md", "哪几套做法的环境前提成立", "内部层次表（《197》四⑥ 同类）"),
    ("xing-fundamental-analyst/SKILL.md", "历史回测、事件时点检验", "内部数据清单表「用途」列（《197》四⑥ 同类）"),
]
def 被人核放过(h):
    for f, frag, why in 人核放过:
        if h["文件"] == f and frag in h["全文"]:
            return why
    return None

卡 = sorted(d for d in os.listdir(包)
            if os.path.isdir(os.path.join(包, d))
            and os.path.exists(os.path.join(包, d, "SKILL.md")))

全命中 = []
for c in 卡:
    根 = os.path.join(包, c)
    文件 = []
    for dp, _, fns in os.walk(根):
        for fn in sorted(fns):
            if fn.endswith(".md") and fn != "common_boundaries.md":
                文件.append(os.path.join(dp, fn))
    文件.sort(key=lambda p: (0 if os.path.basename(p) == "SKILL.md" and os.path.dirname(p) == 根 else 1, p))
    for p in 文件:
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
            for 行名, ws, 正说法 in 禁词表:
                命 = [w for w in ws if w in 行]
                if not 命:
                    continue
                # ---- 形态 ----
                if s.startswith("|"):
                    形态 = "表格单元格"
                elif s.startswith(("│", "┌", "└", "├", "┤", "┬", "┴")):
                    形态 = "箱体画线"
                elif re.search(r"[「『“\"][^「」『』“”\"]*(" + "|".join(map(re.escape, 命)) + ")", 行):
                    形态 = "引号"
                elif 在围栏:
                    形态 = "围栏内"
                else:
                    形态 = "裸正文"
                # ---- 面向用户？（规矩78① 四种命中条件）----
                为什么 = None
                if 用户小节.search(小节):
                    为什么 = f"小节「{小节[:28]}」自己写着给用户看"
                elif 形态 == "箱体画线":
                    为什么 = "箱体输出样例"
                elif 形态 == "表格单元格":
                    # ★★★★★ 同一行里这个词可能出现在**好几个单元格**（❌「不能这么说」/ ✅「要这么说」常常成对），
                    #   ★★★ 只看第一个撞上的格子 → 永远落在「不能这么说」那一列 → **漏报**（1115 第十四轮阳性对照当场抓到）。
                    #   ★★ 所以**每个撞上的格子都要看它自己的列头**，任一格落在面向用户的列就算。
                    cs = 单元格(行)
                    for j, cell in enumerate(cs):
                        if not any(w in cell for w in 命):
                            continue
                        列头 = 表头[j] if 表头 and j < len(表头) else ""
                        if 表头 and 用户列.search(列头):
                            为什么 = f"表格面向用户的列「{列头[:20]}」"
                            break
                elif 形态 == "引号" and 交代句.search(行):
                    为什么 = "引号 + 同一行在交代要怎么说"
                全命中.append(dict(卡=c, 文件=os.path.relpath(p, 包), 行号=i+1, 禁词行=行名,
                                  词=命, 形态=形态, 小节=小节[:40], 原文=s[:120], 全文=s,
                                  否定=bool(否定.search(行)), 面向用户理由=为什么, 正说法=正说法))
                # ★★★ 不 break：★ 同一行可能同时撞两行禁词（如 large_mid + 回测），
                #   ★★ 只记第一条会把另一行的命中吞掉，★★★ 钉死表按片段配也会配不上。

for h in 全命中:
    h["人核放过"] = 被人核放过(h)
    h["判"] = ("⚪ 带否定（在说禁令本身）" if h["否定"] else
               "⚪ 人核放过" if h["人核放过"] else
               "⚪ 尺子看不见这一类（裸正文/内部论证）" if not h["面向用户理由"] else
               "🔴 面向用户")
红 = [h for h in 全命中 if h["判"].startswith("🔴")]

print(f"★ N1 卡数 = {len(卡)}")
print(f"★ N2 宽口径命中 = {len(全命中)} 行（11 行禁词 × 全卡所有 .md，★ 已剔 frontmatter 和 common_boundaries）")
print(f"★ N2b 其中 带否定 {sum(1 for h in 全命中 if h['否定'])} · 人核放过 {sum(1 for h in 全命中 if h['人核放过'] and not h['否定'])}")
print(f"★★★★★ N3 **面向用户**（🔴，这是本闸要拦的数）= {len(红)}")
print("\n=== 形态分类（规矩78 要求打印）===")
分 = {}
for h in 全命中:
    k = (h["形态"], "否定" if h["否定"] else "非否定")
    分[k] = 分.get(k, 0) + 1
for k, v in sorted(分.items(), key=lambda kv: -kv[1]):
    print(f"  {k[0]}/{k[1]}: {v}")
print("\n=== 逐条禁词行 ===")
for 行名, ws, _ in 禁词表:
    g = [h for h in 全命中 if h["禁词行"] == 行名]
    r = [h for h in g if h["判"].startswith("🔴")]
    print(f"  {行名}: 宽 {len(g)} · 🔴 {len(r)}")
if 红:
    print(f"\n=== 🔴 面向用户 {len(红)} 处 ===")
    for h in 红:
        print(f"  {h['文件']}:{h['行号']} [{h['形态']}] {h['面向用户理由']}")
        print(f"      {h['原文'][:100]}")
        print(f"      ✅ 6.12 要的说法：{h['正说法']}")

# ★★★★★ 钉死表自查（规矩79 新增那一条：钉死表自己会烂）
钉 = []
for f, frag, why in 人核放过:
    n = sum(1 for h in 全命中 if h["文件"] == f and frag in h["全文"])
    钉.append(dict(文件=f, 片段=frag, 归类=why, 配上几处=n))
失配 = [e for e in 钉 if e["配上几处"] == 0]
print(f"\n=== 人核钉死表 {len(人核放过)} 条 · 失配 {len(失配)} 条 ===")
for e in 失配:
    print(f"  🟡 配不上了：{e['文件']} ← 「{e['片段'][:30]}」（{e['归类']}）")

out = os.environ.get("XING_OUT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "量禁词_1115.json")
json.dump(dict(卡数=len(卡), 宽口径=len(全命中), 面向用户=len(红),
               看不见的一类="裸正文里对用户说的散句（规矩78③）",
               全命中=全命中, 人核表=钉, 人核表失配=len(失配)),
          open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n★ 落盘 {out}")
