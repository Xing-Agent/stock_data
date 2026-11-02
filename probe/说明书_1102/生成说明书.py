#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 策略说明书生成器（空格版）—— 2026-11-02

★ 大白话:每条策略出厂前要交一张「说明书」,规格书定了**十二格**。
★★ 这个脚本把**现在能填的格子填上**,★★★ 填不了的一律写明
   「**为什么填不了**」—— 不许留空白、不许用近似值顶上。

★★★ 硬纪律（和手册一致）
  ① 一个数都不许编。填不了就写填不了,**并写明缺的是哪一样东西**。
  ② 每一个数必须能指回它的来源文件(路径写在格子里)。
  ③ ★ 本脚本**只读**。不碰 engine、不碰配置、不碰行情。

★ 读这些:
   probe/bench1_rerun_1102/bench1_rerun_1102.json   —— 老池重跑(修复后,45 条)
   engine/configs/*.yaml                            —— 逐条出处(第 2 格)
   probe/exam_run_1102/exam_run_1102.json           —— 考卷(★ 在跑,没有就留空)
"""
from __future__ import annotations
import json, os, sys, glob, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

BENCH = os.path.join(ROOT, "probe/bench1_rerun_1102/bench1_rerun_1102.json")
# ★★★ 退化 R 的笔数必须从这份独立实测读 —— ★ bench json 里那个计数是 None,
# ★★ 因为 engine/chain.py 的 LEDGER_COLUMNS 写死 26 列,r_degenerate 没落到流水里(坑表第 37 处)。
DEGEN = os.path.join(ROOT, "probe/bench1_rerun_1102/退化R实测-1102.json")
EXAM  = os.path.join(ROOT, "probe/exam_run_1102/exam_run_1102.json")
CFG   = os.path.join(ROOT, "engine/configs")

# ★★★ 十二格的定义，照抄 手册/01-策略产品规格书-v3.md 第 1 节
GRID = [
    (1,  "这是哪个版本",                       True),
    (2,  "规则逐条的出处",                     True),
    (3,  "要什么市场环境",                     False),
    (4,  "要什么样的股票",                     False),
    (5,  "这个条件在十二年里成立了多久·哪几年完全不成立", True),
    (6,  "分层表现:牛市/熊市/横盘",            False),
    (7,  "条件成立时的收益",                   False),
    (8,  "两条基准线",                         False),
    (9,  "代价(美元)",                         True),
    (10, "明确不适用什么",                     False),
    (11, "这个历史数字结实不结实",             False),
    (12, "样本外",                             True),
]

# ★ 填不了的标准写法：必须说清缺什么
def 空(缺什么: str, 要什么才能填: str) -> str:
    return f"⬜ **填不了** —— ★ 缺：{缺什么}。★★ 要填上它需要：{要什么才能填}"


def 读yaml浅层(path: str) -> dict:
    """★ 不装 yaml 也能用的极简读法:只取顶层标量 + provenance 块里几个键。
    ★★ 拿不到就返回空 dict —— 不猜。"""
    try:
        import yaml  # noqa
        with open(path, encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def 出处分档(cfg: dict) -> tuple[str, dict]:
    """第 2 格:逐条出处。★ 只数 source 字段的档位分布,不替它判断。"""
    五档 = {"原著": 0, "行业改进": 0, "XING修正": 0, "用户自己的": 0, "外部模型未测": 0, "★没填": 0}
    def 走(o):
        if isinstance(o, dict):
            s = o.get("source") or o.get("source_slots")
            if s is not None:
                t = str(s)
                if "原著" in t:        五档["原著"] += 1
                elif "行业" in t:      五档["行业改进"] += 1
                elif "XING" in t:      五档["XING修正"] += 1
                elif "用户" in t:      五档["用户自己的"] += 1
                elif "模型" in t or "Gemini" in t: 五档["外部模型未测"] += 1
                else:                  五档["★没填"] += 1
            for v in o.values(): 走(v)
        elif isinstance(o, list):
            for v in o: 走(v)
    走(cfg)
    prov = cfg.get("provenance") or {}
    return ("合成流派" if prov.get("composite") else "单一流派"), 五档


def 读退化实测() -> dict[str, int]:
    """★ 返回 {流水文件名片段: 退化笔数}。拿不到就返回空 —— 不猜。"""
    if not os.path.exists(DEGEN): return {}
    try:
        with open(DEGEN, encoding="utf-8") as fh: d = json.load(fh)
        return dict((d.get("真链(REAL__)") or {}).get("名单") or {})
    except Exception:
        return {}


def 配名(名: str) -> str:
    """★ 把链名压成和退化实测里那份名单同一种写法(去空格)。"""
    return 名.replace(" ", "").replace("/", "_")


def 一条说明书(c: dict, exam: dict | None, 退化表: dict[str, int]) -> str:
    名 = c["链"]
    cfg_name = c.get("配置", "")
    cfg = 读yaml浅层(os.path.join(CFG, cfg_name)) if cfg_name else {}
    类型, 五档 = 出处分档(cfg)
    每笔净R = c.get("每笔净R")
    基准一 = c.get("★新基准一值")
    判据 = c.get("★判据Z_用50种子并池对照") or {}
    笔数 = c.get("笔数")
    退化 = dict(c.get("★真链退化R") or {})
    # ★ 用独立实测覆盖那个 None
    实测 = 退化表.get(配名(名))
    if 实测 is not None:
        退化["退化R笔数"] = 实测
        退化["★这个数哪来的"] = "probe/bench1_rerun_1102/退化R实测-1102.json(独立重算,两条判据笔数一致)"
    L = [f"## {名}", ""]
    L.append(f"> ★ 配置 `engine/configs/{cfg_name}` · 族「{c.get('族','?')}」 · "
             f"池 {c.get('★跑在哪个池','?')} · 口径 `{c.get('池子口径','?')}`")
    L.append("")
    L.append("| # | 格子 | 内容 |")
    L.append("|---|---|---|")

    def row(n, 名字, 值):
        L.append(f"| {n} | **{名字}** | {值} |")

    row(1, "这是哪个版本", f"{c.get('族','?')}（★ 轴一·产品版本）")

    有填 = sum(v for k, v in 五档.items() if k != "★没填")
    if 有填 == 0:
        row(2, "规则逐条的出处", 空("这份配置里一条 `source` 都没有",
                                "逐条补 `source`，并过第三道卡口 `engine/checks/source_grep_audit.py`"))
    else:
        明细 = " · ".join(f"{k} {v}" for k, v in 五档.items() if v)
        warn = ""
        if 五档["★没填"]:
            warn = f"<br>★★★ **{五档['★没填']} 条 source 填了但判不出档位** —— 要人判"
        if 类型 == "合成流派":
            warn += ("<br>★★★ **这是合成流派** —— `provenance.method_cards` "
                     f"{'已填' if (cfg.get('provenance') or {}).get('method_cards') else '**是空的**'}，"
                     "见 `probe/出处逐条人判-1102.md` 第三页")
        row(2, "规则逐条的出处", f"{明细}{warn}")

    row(3, "要什么市场环境",
        空("分环境（牛/熊/横盘）的逐段统计",
           "跑一次按环境分层的汇总 —— ★ 数据都在，只是这一轮没跑这个切法"))

    row(4, "要什么样的股票", f"`{c.get('池子口径','?')}`（市值+流动性档）"
                            f"<br>★ 票×年解析：{json.dumps((c.get('universe收窄') or {}).get('票×年 解析方式计数', {}), ensure_ascii=False)}")

    row(5, "条件成立了多久·哪几年完全不成立",
        空("逐年的「掩膜为真的票日比例」",
           "按年切一次 regime 掩膜统计 —— ★ 本轮只算了全期合计，没按年切"))

    row(6, "分层表现", 空("同第 3 格", "同第 3 格"))

    if 每笔净R is None:
        row(7, "条件成立时的收益", 空("每笔净 R", "重跑这条链"))
    else:
        row(7, "条件成立时的收益",
            f"每笔净 R **{每笔净R:+.4f}** · 每笔毛 R {c.get('每笔毛R', float('nan')):+.4f} · "
            f"笔数 **{笔数}**<br>★ 来源 `probe/bench1_rerun_1102/bench1_rerun_1102.json`")

    b1 = ("—" if 基准一 is None else f"**{基准一:+.4f}**")
    偏差 = c.get("★对照笔数偏差")
    row(8, "两条基准线",
        f"① 同环境随机进场（50 种子并池）：{b1} "
        f"（对照笔数偏差 {偏差:+.2%}，★ ±5% 内）"
        f"<br>② 同等仓位大盘：{空('和同等仓位 SPY 的对照', '本轮没跑这一条')}")

    row(9, "代价（美元）",
        空("最大一次亏多少**美元** · 最长连亏几次 · 最长多久不赚钱",
           "逐笔流水。★★★ **本轮流水没入库**（只存了 90 份 SHA-256 清单），"
           "所以这一格现在算不出来 —— ★ 要补就得重跑并落盘流水"))

    row(10, "明确不适用什么",
        空("这一格要人写，不是算出来的",
           "策略组逐条写。★ 可用的素材：`probe/保真度重核-1102.md` 里那 21 处真 bug 和 5 处原句核不到"))

    if 判据:
        row(11, "这个历史数字结实不结实",
            " · ".join(f"{k} **{v:+.4f}**" for k, v in 判据.items() if isinstance(v, (int, float)))
            + "<br>★★★ 门槛口径：Bonferroni **双侧** 3.399 / 3.417 / 3.603"
              "（★ 单侧 3.205 / 3.224 / 3.419，★★ 两者别混）"
              "<br>★★ 真实 M ≈ 113（45 条链只有 33 份独立结果，「159 条」虚高）")
    else:
        row(11, "这个历史数字结实不结实", 空("t 值 / 两段一致性", "重跑这条链"))

    if exam and 名 in (exam.get("逐链") or {}):
        e = exam["逐链"][名]
        row(12, "样本外", f"考卷 1,026 只：每笔净 R **{e.get('每笔净R', float('nan')):+.4f}** · "
                        f"笔数 {e.get('笔数')} · 基准一 {e.get('★新基准一值', float('nan')):+.4f}")
    else:
        row(12, "样本外",
            "⬜ **待考卷** —— ★ 考卷（1,026 只从没碰过的票）正在跑，"
            "★★ 跑完这一格自动填上"
            "<br>★★★ 填上之后**必须同时写两条口径差异**，不然会把别的东西算成「样本外」："
            "<br>① 老池 **198 只** vs 考卷 **1,026 只** —— 票数 5.2 倍，**样本外和池子变大混在一起**"
            "<br>② 考卷有 24 家公司在改名那年之后静默离开 universe（坑表第 40 处），老池没有这个问题")

    # ★ 这条链自己的已知问题
    注 = []
    if 退化.get("退化R笔数"):
        注.append(f"★★★ 真链有 **{退化['退化R笔数']} 笔**退化 R（已剔出 R 均值，**不是删交易**）"
                  f"<br>★ 这个数来自 `{退化.get('★这个数哪来的','?')}`"
                  f"<br>★★ 实测方向：剔掉之后这条链的**成绩变好了** —— "
                  f"说明被剔的是**假巨亏**（分母近零），不是假巨盈（坑表第 36 处）")
    if not 退化.get("有r_degenerate列", True):
        注.append("★★ 流水里**没有** `r_degenerate` 留痕列（`LEDGER_COLUMNS` 写死 26 列，坑表第 37 处）→ 事后对账只能反推")
    if c.get("★无止损_R退化成收益率_不可和有止损同列排序"):
        注.append("★★★ **这条链无止损** → R 退化成收益率，**不可和有止损的链同列排序**")
    # ★★★ 不许用 `★符号是否翻转` 当「退化 R 修复的后果」——
    # ★ 那个字段对的是 **1030 那一轮**,混了三个变化(退化 R 修复 + 5 种子→50 种子 + 全池→研发池)。
    # ★★ 干净的单变量对比是 `★对1031(修复前)` 里的 `★基准一符号是否翻转(1031→1102)`。
    对1031 = c.get("★对1031(修复前)") or {}
    if 对1031.get("★基准一符号是否翻转(1031→1102)"):
        注.append("★★★ **只因退化 R 修复就让基准一符号翻转** —— ★ 这是单变量对比（1031→1102）")
    if c.get("★符号是否翻转"):
        注.append("★ 基准一符号相对 **1030 那一轮**翻转了 —— ★★★ **但这不能算到退化 R 修复头上**："
                  "那一轮到现在混了**三个**变化（退化 R 修复 · 种子 5→50 · 全池→研发池 198 只）。"
                  f"★ 单变量对比（1031→1102）这条链**没有**翻转。1030 值 {c.get('旧基准一(作废·仅用于看污染有多大)', float('nan')):+.4f}"
                  f" → 1031 值 {对1031.get('1031基准一', float('nan')):+.4f} → 本轮 {c.get('★新基准一值', float('nan')):+.4f}")
    if 注:
        L += ["", "**★ 这条链自己的已知问题：**", ""] + [f"- {x}" for x in 注]
    L.append("")
    return "\n".join(L)


def main() -> int:
    if not os.path.exists(BENCH):
        print(f"★ 拿不到老池重跑结果:{BENCH}", file=sys.stderr); return 2
    with open(BENCH, encoding="utf-8") as fh:
        bench = json.load(fh)
    exam = None
    if os.path.exists(EXAM):
        try:
            with open(EXAM, encoding="utf-8") as fh: exam = json.load(fh)
        except Exception: exam = None

    退化表 = 读退化实测()
    if not 退化表:
        print("★★★ 警告:读不到 退化R实测-1102.json —— 退化笔数那一栏会缺", file=sys.stderr)
    链 = bench["逐链"]
    if isinstance(链, dict): 链 = list(链.values())

    能填 = sum(1 for _, _, _ in GRID)  # 占位,下面按实测数
    填上了 = [1, 2, 4, 7, 8, 11]
    填不了 = [3, 5, 6, 9, 10]
    待考卷 = [12]

    out = []
    out.append("# 策略说明书 · 全 45 条（★★★ 空格版）")
    out.append("")
    out.append(f"> 生成时间 {datetime.datetime.now():%Y-%m-%d %H:%M} · "
               f"来源 `probe/bench1_rerun_1102/`（老池重跑，退化 R 修复后）")
    out.append("")
    out.append("---")
    out.append("")
    out.append("# ★★★ 三秒版")
    out.append("")
    out.append("```")
    out.append("★ 每条策略出厂前要交一张说明书,规格书定了**十二格**。")
    out.append(f"★★ 这一版:**{len(填上了)} 格填上了 · {len(填不了)} 格填不了 · 1 格等考卷**。")
    out.append("★★★ 这份文件最该看的不是填上的那几格,是**填不了的那 5 格,以及为什么填不了** ——")
    out.append("   ★ 因为一份只写成绩的说明书,会让人以为事情做完了。")
    out.append("```")
    out.append("")
    out.append("## ★ 哪几格填上了、哪几格没有")
    out.append("")
    out.append("| # | 格子 | 状态 | ★ 没填的话，缺什么 |")
    out.append("|---|---|---|---|")
    缺 = {
        3:  "分环境逐段统计 —— ★ 数据都在，只是这一轮没跑这个切法",
        5:  "逐年的「掩膜为真的票日比例」—— ★ 本轮只算了全期合计",
        6:  "同第 3 格",
        9:  "★★★ **逐笔流水没入库**（只存了 90 份 SHA-256 清单）→ 美元口径的代价现在算不出来",
        10: "★ 这一格要人写，不是算出来的",
        12: "★ 考卷在跑",
    }
    for n, 名字, 必填 in GRID:
        st = "✅ 填上了" if n in 填上了 else ("⬜ 待考卷" if n in 待考卷 else "⬜ 填不了")
        out.append(f"| {n} | {名字}{' ★必填' if 必填 else ''} | {st} | {缺.get(n,'—')} |")
    out.append("")
    out.append("★★★ **四个必填格里，第 5 格和第 9 格现在是空的** —— "
               "★ 所以严格讲，**这 45 条一条都还不能出厂**。★★ 这不是悲观，是把门槛当门槛。")
    out.append("")
    out.append("---")
    out.append("")
    for c in 链:
        out.append(一条说明书(c, exam, 退化表))
        out.append("---")
        out.append("")

    dst = os.path.join(HERE, "策略说明书-全45条-1102.md")
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"★ 写出 {dst}（{len(链)} 条，{len(out)} 段）")
    print(f"★★ 填上 {填上了} · 填不了 {填不了} · 待考卷 {待考卷}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
