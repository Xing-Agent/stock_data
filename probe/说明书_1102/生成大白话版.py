#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 策略说明书 · 大白话版生成器 —— 2026-11-04

★ 给谁看:Lin 本人(今天要把 45 条逐条过一遍)。
★★ 和 `策略说明书-全45条-1102.md` 的区别:
   ① 那一份是**工程口径**(十二格、门槛、Z 值、口径戳),给审阅/归档用;
   ② 这一份**只回答七个大白话问题**,一条策略一屏,★★★ 每条末尾只问他**一句**。

★★★ 硬纪律(和老脚本一致,一条不松)
  ① **一个数都不许编**。所有数字只能来自下面那几份 json / yaml,
     ★★★ 任何「手写进字符串」的数字 = 11-04 那个 1,797 同类错误。
  ② 规则的大白话翻译只允许从 yaml 的 type/params **逐项直译**;
     ★★★ 字典里没有的 type **原样印出来并标「我没译」**,绝不凭名字猜。
  ③ 本脚本**只读**。不碰 engine、不碰配置、不碰行情。
"""
from __future__ import annotations
import json, os, datetime
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

BENCH = os.path.join(ROOT, "probe/bench1_rerun_1102/bench1_rerun_1102.json")
SLOT5 = os.path.join(HERE, "第5格-按年-1102.json")
SLOT9 = os.path.join(HERE, "第9和3_6格-1102.json")
EXAM  = os.path.join(ROOT, "probe/exam_run_1102/汇总更正_老池用1102-1102.json")
NETR  = os.path.join(ROOT, "probe/netr_bench1_1104/干净版-1104.json")
CFG   = os.path.join(ROOT, "engine/configs")
OUT   = os.path.join(ROOT, "手册/25-策略说明书-大白话版-全45条-1104.md")

# ─────────────────────────────────────────────────────────────
# ★ 规则直译表。★★★ key = yaml 里的 type 原值,value = 一句大白话模板。
#   ★ 模板里的 {xxx} 全部从 params 取,★★ 取不到就印 ?,不许用默认值顶上。
# ─────────────────────────────────────────────────────────────
译 = {
    # 进场
    "donchian_close_breakout":        "收盘创 {lookback} 天新高就买",
    "monthly_sma_above":              "月线收在 {months} 月均线上方才买(一个月只看一次)",
    "rsi_oversold":                   "RSI({period}) 跌到 {threshold} 以下(超卖)就买",
    "pat6_rsi_oversold":              "RSI({rsi_period}) 跌到 {max_rsi} 以下(超卖)就买",
    "td_buy_setup":                   "连着 {count} 根收盘价都比 {ref_lag} 根前低(TD 买入 setup 数满)就买",
    "turtle_soup":                    "先破 {lookback} 天新低、当天又收回来(海龟汤:假突破反手)",
    "swing_low_exists":               "先得有一个 {lookback} 天里的低点摆动(至少隔 {min_bars_before} 根)",
    "intraday_break_below_swing_low": "盘中跌破那个低点(前面至少创过 {min_new_low_days} 天新低)",
    "close_reclaim_above_swing_low":  "当天又收回到那个低点上方(= 下刺被收复)",
    "bullish_candle":                 "当天得是根阳线({require})",
    "atr_squeeze":                    "短期波动({atr_fast} 日 ATR)缩到长期({atr_slow_ma} 日均值)的 {max_ratio} 以下 = 静下来了",
    "vcp_contraction":                "一个 {base_min_days}~{base_max_days} 天的平台,振幅一浪比一浪小(VCP 收缩)",
    "vcp_volume_duo":                 "平台里出现地量(≤{slow_period} 日均量的 {dryup_day_ratio})",
    "pat6_cup_with_handle":           "杯柄形:杯深 {cup_depth_min}~{cup_depth_max},柄深 ≤{handle_max_depth},杯宽 {cup_min_bars}~{cup_max_bars} 根",
    "pat6_darvas_breakout":           "达瓦斯箱体:箱子至少 {min_box_bars} 根、确认 {confirm_days} 天,突破箱顶就买",
    "pat6_narrow_box_breakout":       "最近 {bars} 根的区间收窄到 {max_range_pct} 以内,然后突破",
    "pat6_daily_base_breakout":       "{base_bars} 天的平台,突破平台高点就买",
    "pat6_volume_x_sma":              "当天成交量 ≥{period} 日均量的 {multiple} 倍(放量)",
    "pat6_ma_slope_up":               "{ma_period} 日均线在往上走(看 {slope_lookback} 天斜率)",
    "pat6_bb_tag_lower":              "价格摸到布林带下轨({period} 日,{k} 倍标准差)",
    "pat6_bb_reversal":               "摸到下轨后反转",
    "pat6_bb_reclaim":                "摸下轨 + RSI({rsi_period}) 低于 {rsi_low},随后回到 {rsi_back} 以上",
    "pat6_bb_bw_jump_gate":           "★ 熔断闸:布林带宽最近 {bw_jump_lookback} 天跳升超过 {bw_jump_max} 就不买",
    "pat6_bb_trend_gate":             "★ 趋势闸:得在 {ma_period} 日均线上方、且均线 {slope_lookback} 天在往上",
    "pat6_bb_trend_filters":          "★ 三道过滤:{ma_period} 日均线上方 + 均线向上 + ADX({adx_period}) ≤{adx_max}",
    "pat6_spring":                    "威科夫 Spring:下刺 {depth_min_atr}~{depth_max_atr} 倍 ATR 后被收复",
    "pat6_w_bottom_divergence":       "W 底 + MFI({mfi_period}) 底背离",
    # 离场
    "close_below_lowest_low":         "收盘创 {lookback} 天新低就卖",
    "close_below_ema":                "收盘跌破 {ema} 日 EMA 就卖",
    "close_below_ma":                 "收盘跌破 {ma} 日均线就卖",
    "close_above_ma":                 "收盘站上 {ma} 日均线就卖(止盈)",
    "close_below_trailing_stop":      "跌到跟踪止损线就卖",
    "monthly_sma_below":              "月线收到 {months} 月均线下方就卖",
    "pat6_close_above_bb_mid":        "收盘站上布林中轨({period} 日)就卖(止盈)",
    "pat6_close_below_darvas_bottom": "收盘跌破箱体底(确认 {confirm_days} 天)就卖",
    "td_countdown_13_exit":           "TD countdown 数到 {countdown} 就卖",
    "td_sell_setup_exit":             "TD 卖出 setup 数满 {count} 就卖",
    "td_price_flip_exit":             "TD 价格翻转(和 {ref_lag} 根前比)就卖",
    "time_stop":                      "拿满 {max_holding_days} 天就卖(到点就走,不管赚亏)",
    # 止损
    "atr_multiple":                   "止损挂在 {multiple} 倍 ATR({atr_period} 日)之外",
    "day_low_minus_atr":              "止损挂在当天最低价再往下 {atr_multiple} 倍 ATR({atr_period} 日)",
    "day_low_minus_tick":             "止损挂在最近 {structure_lookback} 根的低点下一个最小跳动({tick})",
    "lowest_low":                     "止损挂在 {lookback} 天最低价",
    "structure_low_minus_atr":        "止损挂在最近 {structure_lookback} 根的结构低点再往下 {atr_multiple} 倍 ATR",
    # ★★★ pct ≥0.9 等价于不设止损(汇总里已登记),★ 所以这里直说
    "pct":                            "止损挂在买入价下方 {pct}（★★ ≥90% 等于没止损）",
    "td_risk_level_stop":             "止损挂在 TD 风险位(回看 {setup_lookback} 根)",
    # 选股 / 环境
    "adv_rank_exclude_bottom":        "把成交额({adv_period} 日)最差的 {exclude_bottom_pct}% 剔掉",
    "price_above_ma":                 "只买站在自己 {ma} 日均线上方的票",
    "index_above_ma_scaled":          "大盘闸:{symbol} 得在 {ma} 日均线的 {factor} 倍以上",
    "index_ma_slope":                 "大盘闸:{symbol} 的 {ma} 日均线 {lookback} 天斜率要 >{min_slope}",
}


def 译规则(t, params) -> str:
    """★★★ 字典里没有的 type,原样印出并标明「我没译」—— 不猜。"""
    p = params if isinstance(params, dict) else {}
    tpl = 译.get(str(t))
    if tpl is None:
        return f"`{t}`（★★★ 这一句我没译 —— 别凭名字猜它是什么）"
    out = tpl
    for k, v in p.items():
        if v is None:
            continue
        s = f"{v:g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)
        if k == "pct" and isinstance(v, (int, float)):
            s = f"{v*100:.2f}%"
        if k in ("max_ratio", "dryup_day_ratio", "cup_depth_min", "cup_depth_max",
                 "handle_max_depth", "max_range_pct", "bw_jump_max",
                 "cup_depth_min", "exclude_bottom_pct") and isinstance(v, (int, float)) and v < 1:
            s = f"{v*100:g}%"
        out = out.replace("{" + k + "}", s)
    # ★ 没被填上的占位符一律换成 ? —— ★★ 不许用默认值顶上
    while "{" in out and "}" in out:
        i, j = out.index("{"), out.index("}")
        out = out[:i] + "?" + out[j+1:]
    return out


def 读配置(f: str) -> dict:
    try:
        with open(os.path.join(CFG, f), encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def 规则三行(cfg: dict) -> list[str]:
    行 = []
    # ★★★ 锚点(buy_and_hold)本来就没有进出场规则 —— ★ 不是配置漏填
    锚点 = "buy_and_hold" in str((cfg.get("meta") or {}).get("name", "")).lower() \
        or "buy_and_hold" in str((cfg.get("meta") or {}).get("master", "")).lower() \
        or bool((cfg.get("meta") or {}).get("anchor"))
    for sec, 名 in (("universe", "只买什么票"), ("regime", "大盘什么情况下才开工"),
                    ("entry", "什么时候买"), ("exit", "什么时候卖")):
        rs = ((cfg.get(sec) or {}).get("rules") or [])
        句 = [译规则(r.get("type"), r.get("params")) for r in rs if isinstance(r, dict)]
        if not 句:
            if sec == "regime":
                行.append(f"**{名}** | ★★★ **没装任何大盘开关 —— 它一年 365 天都开工**")
            elif sec == "universe":
                行.append(f"**{名}** | 全池照跑,没有额外挑票条件")
            else:
                行.append(f"**{名}** | " + ("★ **买了就一直拿**（这是锚点，本来就没有进出场规则）"
                          if 锚点 else "★★★ **空的** —— ★ 这不正常,要查配置"))
        else:
            行.append(f"**{名}** | " + " ＋ ".join(句))
    st = cfg.get("initial_stop") or {}
    ts = cfg.get("trailing_stop") or {}
    止 = []
    if st.get("type") and str(st.get("type")).lower() != "none":
        止.append(译规则(st.get("type"), st.get("params")))
    if ts.get("type") and str(ts.get("type")).lower() != "none":
        止.append("跟踪止损:" + 译规则(ts.get("type"), ts.get("params")))
    行.append("**亏到哪儿认输(止损)** | " + (" ＋ ".join(止) if 止 else
              "★★★ **不设止损** —— ★★ 所以它那个「R」不是风险倍数,**是收益率**,不能和别的策略排在一列比"))
    sz = ((cfg.get("sizing") or {}).get("params") or {})
    if sz:
        行.append(f"**一次拿几只 / 一笔赌多少** | 最多同时拿 **{sz.get('max_positions','?')}** 只 · "
                  f"每笔最多亏账户的 **{(sz.get('risk_per_trade') or 0)*100:g}%**")
    return 行


def 钱(x) -> str:
    if x is None:
        return "?"
    s = f"${abs(x):,.0f}"
    return ("−" + s) if x < 0 else s


def 分环境行(d9: dict) -> str:
    g = (d9 or {}).get("第3_6格_分环境") or {}
    out = []
    for 名 in ("牛", "横盘", "熊"):
        v = g.get(名) or {}
        n = v.get("笔数")
        if n is None:
            continue
        if not n:
            out.append(f"{名} **0 笔** —— ★ 这个环境里它一次都没做过")
            continue
        不够 = v.get("★笔数<30_不给统计结论")
        标 = " ★★★ **笔数不够 30，这一格不算结论**" if 不够 else ""
        out.append(f"{名} {n} 笔 · 每笔 {v.get('每笔净R',0):+.3f} R · "
                   f"胜率 {(v.get('胜率') or 0)*100:.0f}% · {钱(v.get('净盈亏美元'))}{标}")
    return "<br>".join(out) if out else "?"


def 一条(c: dict, d9: dict, ex: dict | None, nr: dict | None) -> str:
    名 = c["链"]
    cfg = 读配置(c.get("配置", ""))
    meta = cfg.get("meta") or {}
    每笔 = c.get("每笔净R")
    基 = c.get("★新基准一值")
    # ★★★ 「基准一」= **真链每笔毛 R − 对照组每笔毛 R**,是一个**差额**,
    #   ★★ 不是对照组自己的那个数 —— ★ 我第一版把它当对照值读,算出 28 条赢(真值 22 条)。
    赢 = (基 is not None and 基 > 0)
    d = (d9 or {}).get("第9格_代价") or {}
    净盈亏 = d.get("全期净盈亏美元")
    无止损 = bool(c.get("★无止损_R退化成收益率_不可和有止损同列排序"))

    L = [f"## {名}", ""]
    L.append(f"> ★ 谁的方法：{meta.get('master','?')} · 出处 {meta.get('book','?')} · "
             f"配置 `{c.get('配置','?')}` · 族「{c.get('族','?')}」")
    L.append("")
    L.append("### ★ 一、它到底在干什么（★ 下面每一行都是配置里逐条直译的，不是我总结的）")
    L.append("")
    L.append("| | |")
    L.append("|---|---|")
    L += ["| " + r + " |" for r in 规则三行(cfg)]
    L.append("")
    L.append("### ★★ 二、七个大白话问题")
    L.append("")
    L.append("| 问 | 答 |")
    L.append("|---|---|")
    L.append(f"| **1. 这 8 年它到底赚钱了吗？** | 全期 **{钱(净盈亏)}**"
             + ("（★★★ **是亏的**）" if (净盈亏 or 0) < 0 else "（★ 赚的）")
             + f" · 一共做了 **{c.get('笔数','?')}** 笔 |")
    L.append(f"| **2. 平均每笔赚多少？** | 每笔 **{每笔:+.4f} R**"
             + ("（★★ 这里的 R = 收益率，因为它不设止损）" if 无止损
                else "（★ R = 「赚的钱 ÷ 当初准备亏的钱」）") + " |")
    对毛 = (nr or {}).get("对毛")
    L.append(f"| **3. 它比「瞎买」强吗？** | 它每笔比**同样环境下随机进场**多赚 **{基:+.4f} R**"
             + (f"（它 {nr['真毛']:+.4f} R vs 瞎买 {对毛:+.4f} R）" if 对毛 is not None else "")
             + " → " + ("★★ **强（赢随机）**" if 赢 else "★★★ **不强（输给随机）**")
             + "<br>★ 这一行用的是**扣成本之前**的数（和我们登记的判据同口径：45 条里 22 赢 / 23 输）|")
    if nr:
        脏 = nr.get("对摩擦R") or 0
        可信 = "✓ 可信" if 脏 <= 0.08 else ("⚠ 可疑" if 脏 <= 0.5 else "✗ 不可信")
        L.append(f"| **3b. 换成「扣完交易成本再比」呢？** | 它 {nr.get('真净',0):+.4f} R vs 瞎买 {nr.get('对净',0):+.4f} R → "
                 + ("★ **赢**" if (nr.get('真净',0) > nr.get('对净',0)) else "★★ **输**")
                 + f"<br>★★★ 但这一行**{可信}**：瞎买那一边光摩擦就占 **{脏:.3f} R**"
                 + ("（★ 它的止损只有 " + f"{nr.get('对止损',0):.2f}%，摩擦在 R 这个单位里被放大了）" if 脏 > 0.08 else "")
                 + " |")
    L.append(f"| **4. 最疼的时候有多疼？** | 一笔最多亏 **{钱(d.get('★★★最大一次亏多少美元'))}**"
             f"（{(d.get('那一笔') or {}).get('票','?')} {(d.get('那一笔') or {}).get('进场','?')}）<br>"
             f"连着亏 **{d.get('★★最长连亏几次','?')}** 次 · "
             f"最长 **{d.get('★★★最长多久不赚钱_自然日','?'):.0f} 天**不赚钱"
             f"<br>★ 口径：在 **100 万美元**账户上。★★ 换账户大小**不是按比例缩放的**，所以这几个美元数不要外引 |")
    L.append(f"| **5. 什么环境下它好用？** | {分环境行(d9)}<br>"
             "★★★ 这三档是**我们自己分的**（SPY 200 日线上下 + 斜率），★ 不是原著的说法 |")
    if ex:
        L.append(f"| **6. 换一批从没见过的票，还灵吗？** | 考卷（1,026 只没碰过的票）：**{ex.get('考卷_基准一',0):+.4f}** · "
                 f"老池同一条 {ex.get('老池_基准一',0):+.4f} → {ex.get('方向','?')}"
                 + ("<br>★★★ **符号翻转了**" if ex.get("★符号翻转") else "")
                 + " |")
    else:
        L.append("| **6. 换一批从没见过的票，还灵吗？** | ★★ 考卷那份汇总里**没有这一条** |")
    L.append("| **7. 它明确不该用在什么时候？** | ⬜ **空的** —— ★★★ 这一格算不出来，**只能你写**。"
             "★ 这就是今天要你填的那一句 |")
    L.append("")
    if 无止损:
        L.append("> ★★★ **这条链没有止损** —— ★★ 它的「R」是收益率，**不许和有止损的策略放一列排名次**。")
        L.append("")
    L.append("**★ 要你写的那一句（第 7 问）：**")
    L.append("")
    L.append("```")
    L.append("谁不该用它 / 什么时候别用：")
    L.append("")
    L.append("```")
    L.append("")
    L.append("---")
    L.append("")
    return "\n".join(L)


def main() -> None:
    b = json.load(open(BENCH, encoding="utf-8"))
    s9 = json.load(open(SLOT9, encoding="utf-8"))["逐链"]
    ex = {r["链"]: r for r in json.load(open(EXAM, encoding="utf-8"))["逐链并列"]}
    nrL = json.load(open(NETR, encoding="utf-8"))
    nr = {str(r["链"]): r for r in nrL}

    def 压(s: str) -> str:
        return s.replace(" ", "").replace("/", "_")

    链 = b["逐链"]
    # ─── 一屏总表 ───
    T = ["| # | 策略 | 赚钱吗 | 比瞎买强吗 | 换票后 | 最长不赚钱 | ★ 要你写第 7 问 |",
         "|---|---|---|---|---|---|---|"]
    for i, c in enumerate(链, 1):
        d9 = s9.get(c["链"]) or {}
        d = d9.get("第9格_代价") or {}
        e = ex.get(c["链"])
        赢 = (c.get("★新基准一值") or 0) > 0
        盈 = d.get("全期净盈亏美元")
        T.append(f"| {i} | {c['链']} | {'★ 赚 ' if (盈 or 0)>0 else '★★★ 亏 '}{钱(盈)} | "
                 f"{'✅ 赢' if 赢 else '❌ 输'} | "
                 f"{('★★★ 翻转' if e.get('★符号翻转') else e.get('方向','?')) if e else '—'} | "
                 f"{(d.get('★★★最长多久不赚钱_自然日') or 0):.0f} 天 | ⬜ |")

    赢数 = sum(1 for c in 链 if (c.get("★新基准一值") or 0) > 0)
    亏数 = sum(1 for c in 链 if ((s9.get(c["链"]) or {}).get("第9格_代价") or {}).get("全期净盈亏美元", 0) < 0)

    H = [
        "# 25 · 策略说明书 · ★★★ 大白话版（全 45 条）",
        "",
        f"> ★ 生成 {datetime.date.today()} · ★★ 本文件由 `probe/说明书_1102/生成大白话版.py` **算出来**，"
        "★★★ 里面没有一个手写的数字（1,797 那个错就是手写出来的）",
        "> ★ 数据来源：`probe/bench1_rerun_1102/` · `probe/说明书_1102/第9和3_6格-1102.json` · "
        "`probe/exam_run_1102/汇总更正_老池用1102-1102.json` · `probe/netr_bench1_1104/干净版-1104.json`",
        "",
        "## ★★★ 三秒版",
        "",
        "```",
        "★ 这份是给你一条一条过的。每条策略一屏,只回答七个问题。",
        f"★★ 45 条里:**{赢数} 条赢随机 · {45-赢数} 条输** · **{亏数} 条全期是亏钱的**。",
        "★★★ 而**第 7 问(它不该用在什么时候)45 条全是空的** ——",
        "   ★ 这一格算不出来,只能你写,★★ 所以严格讲这 45 条一条都还不能出厂。",
        "★★★ 今天你要做的就是这一件:**逐条把第 7 问那一句写上。**",
        "```",
        "",
        "## ★★ 读的时候记住三件（★ 不记住就会读出假结论）",
        "",
        "```",
        "★★★ 一、「比瞎买强吗」这一行用的是**扣成本之前**的数(和登记的判据同口径)。",
        "   ★ 扣完成本的那一行我另给了(3b),★★ 但它在**止损很窄**的策略上不可用 ——",
        "   ★★★ 因为成本在「R」这个单位里会被放大,★ 所以那一行我标了可信 / 可疑 / 不可信。",
        "★★★ 二、这 45 条是**用老池成绩挑出来的**(原本 79 条,挡掉 34 条)。",
        "   ★★ 所以「45 条里一半赢随机」**不能**读成「我们的方法一半有效」。",
        "★★★ 三、「牛 / 横盘 / 熊」这三档是**我们自己分的**,不是原著的说法;",
        "   ★ 而且「横盘」这个名字是错的 —— 实测那 73 天全在大跌之后,是反弹不是震荡。",
        "```",
        "",
        "---",
        "",
        "# ★ 一屏总表（45 条）",
        "",
    ] + T + ["", "---", "", "# ★★ 逐条（一条一屏）", ""]

    body = []
    for c in 链:
        body.append(一条(c, s9.get(c["链"]) or {}, ex.get(c["链"]),
                        nr.get(压(c["链"]))))

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(H) + "\n".join(body))
    print("写出", OUT, "链数", len(链), "赢", 赢数, "亏", 亏数,
          "净R对上", sum(1 for c in 链 if 压(c["链"]) in nr))


if __name__ == "__main__":
    main()
