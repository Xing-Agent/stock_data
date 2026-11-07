# -*- coding: utf-8 -*-
"""
★★★ A 路（23 条基本面）补的第三层覆盖层 —— ★ engine 零改动（进程内替换函数指针）。

★ 三秒版:前两层(新财报库 + 9 指标 8 规则)只够「把票筛进池子」;
  ★★ 要把基本面卡**原样跑成策略**,还差四样东西,这一层补上:
    ① 排序(槽位不够时先买谁)  ② 「不再满足就卖」的离场
    ③ 几个卡上要、前两层没有的指标/规则  ④ 茨威格「大盘红绿灯」

★★★ 为什么 ① 排序是要命的一件(★ 查代码查出来的,不是猜的):
  `matrices.rank_score_matrix` 在配置没写 rank_by 时**默认按 126 日涨幅排**
  (`matrices.py:1160`)—— ★★ 也就是说,池子里便宜股有几百只、槽位只有 30 个时,
  **引擎会悄悄挑「最近涨得最猛」的那 30 只**。★★★ 这等于给每条价值策略偷偷加了
  一道动量闸 —— 原著里没有。→ 这一层让配置能写「按市盈率从低到高」之类的原著排序。

★★★ 还有一件同样要命的(★ 也是查代码查出来的):
  《84》说「引擎允许空进场(entry.rules: [])= 在池子里就买」——
  ★★ 校验器确实不报错,**但 `entry_trigger` 遇到空 rules 会落到 `type` 默认值 "never"**
  (`matrices.py:986` `t = spec.get("type", "never")`)→ ★★★ **一笔都不会买**。
  → 正确写法是 `entry: { type: always }`(`matrices.py:1014`)。范本 基-4 已改。

★★ 铁律(照抄前两层):认不出的类型**原样转回原函数**;NaN 一律判不合格;
  生效时点 = filing_date + 1 个交易日(走 engine.fundamentals 的同一条路径)。
"""
from __future__ import annotations

import os, sys
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_装过 = False

新指标 = (
    "liab_to_eq",        # ★ 总负债 / 股东权益(施洛斯「没有高负债」)
    "current_ratio",     # ★ 流动比率(格雷厄姆 ≥ 2)
    "ltd_over_nwc",      # ★ 长期债 / 净流动资产(格雷厄姆 ≤ 1)
    "ni_pos_years",      # ★ 连续几年年度净利润 > 0(按 TTM 每 4 季回看)
    "div_years",         # ★ 连续几年有分红(按 TTM 每 4 季回看)
    "eps3_avg_ps",       # ★ 近三年平均每股收益(格雷厄姆市盈率的分母)
    "rev_ttm",           # ★ 营收 TTM(格雷厄姆「规模足够大」)
    "roce",              # ★ EBIT / (总资产 − 流动负债)(特里·史密斯)
    "gross_margin",      # ★ 毛利率
    "fcf_conv",          # ★ 自由现金流 / 净利润(现金转化率)
    "eps_q_yoy",         # ★ 单季每股收益同比增速(茨威格)
    "rev_q_yoy",         # ★ 单季营收同比增速(茨威格)
)


def _连续年数(s: pd.Series) -> pd.Series:
    """★ 每一期往回数:t、t−4、t−8 … 连续 > 0 的有几年。★ 本期 NaN → NaN。"""
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        if not np.isfinite(v[i]):
            continue
        k, j = 0, i
        while j >= 0 and np.isfinite(v[j]) and v[j] > 0:
            k += 1
            j -= 4
        out[i] = k
    return pd.Series(out, index=s.index)


def _单季(F, symbol, metric, idx):
    try:
        obs = F.quarterly(symbol, metric)
    except Exception:
        return None
    if not obs:
        return None
    s = pd.Series({o.period_end: o.value for o in obs}).dropna()
    return s.reindex(idx) if len(s) else None


def metric_quarterly(F, P, symbol, name, vals, ef):
    空 = (pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]"))
    if vals is None or vals.empty:
        return 空
    # ★★ 生效日表先统一成日期类型 —— 原表里全空的列是 float,和日期混在一起取 max 会抛错
    #   (★ 1106 晚实测:研发池 60 只里 53 只因此抛错、被上层吞成「算不出」)
    ef = ef.apply(pd.to_datetime, errors="coerce")
    生效 = ef.max(axis=1)        # ★ 保守:用到的列里最晚的那个(下面逐个按需收紧)

    def 收(v, cols=None):
        v = v.replace([np.inf, -np.inf], np.nan)
        e = ef[cols].max(axis=1) if cols else 生效
        return v, e.reindex(v.index)

    has = lambda *c: all(x in vals.columns for x in c)   # noqa: E731
    sh = vals["shares"].where(vals["shares"] > 0) if has("shares") else None

    if name == "liab_to_eq":
        eq = vals["eq"].where(vals["eq"] > 0)
        return 收(vals["liab"] / eq, ["liab", "eq"])
    if name == "current_ratio":
        return 收(vals["ca"] / vals["cl"].where(vals["cl"] > 0), ["ca", "cl"])
    if name == "ltd_over_nwc":
        nwc = (vals["ca"] - vals["cl"])
        return 收(vals["ltd"] / nwc.where(nwc > 0), ["ltd", "ca", "cl"])
    if name == "ni_pos_years":
        return 收(_连续年数(vals["ni"]), ["ni"])
    if name == "div_years":
        d, e = P.metric_quarterly(F, symbol, "div_ttm_ps", vals, ef)
        if len(d) == 0:
            return 空
        return _连续年数(d.reindex(vals.index)), e.reindex(vals.index)
    if name == "eps3_avg_ps":
        eps = vals["ni"] / sh
        return 收((eps + eps.shift(4) + eps.shift(8)) / 3.0, ["ni", "shares"])
    if name == "rev_ttm":
        return 收(vals["rev"], ["rev"])
    if name == "roce":
        cap = vals["ta"] - vals["cl"]
        return 收(vals["ebit"] / cap.where(cap > 0), ["ebit", "ta", "cl"])
    if name == "gross_margin":
        return 收((vals["rev"] - vals["cor"]) / vals["rev"].where(vals["rev"] > 0),
                 ["rev", "cor"])
    if name == "fcf_conv":
        f, fe = F.metric_quarterly(symbol, "fcf_ttm")
        if len(f) == 0:
            return 空
        f = f.reindex(vals.index)
        ni = vals["ni"].where(vals["ni"] > 0)
        e = pd.concat([pd.to_datetime(fe.reindex(vals.index), errors="coerce"), ef["ni"]],
                      axis=1).max(axis=1)
        return (f / ni).replace([np.inf, -np.inf], np.nan), e
    if name in ("eps_q_yoy", "rev_q_yoy"):
        m = "NetIncome" if name == "eps_q_yoy" else "Revenue"
        q = _单季(F, symbol, m, vals.index)
        if q is None:
            return 空
        if name == "eps_q_yoy":
            q = q / sh                       # ★ 每股口径(摊薄股数)
        base = q.shift(4)
        # ★★ 基数 ≤ 0 时增速没有意义 → NaN(★ 不取绝对值,那会造出假的高增速)
        g = (q - base) / base.where(base > 0)
        col = "ni" if name == "eps_q_yoy" else "rev"
        return 收(g, [col, "shares"] if name == "eps_q_yoy" else [col])
    return 空


# ════════════════════════════════════════════════════════════════════
# 选股规则
# ════════════════════════════════════════════════════════════════════
新规则 = ("pb_rank_bottom", "fund_metric_threshold", "graham_defensive",
          "value_momentum_top", "zweig_garp", "roce_rank_top_x",
          "magic_formula_available")


def _pct(x):
    return x.rank(axis=1, pct=True)


def _mom_12_1(close):
    """★ 12-1 月动量:过去第 2~12 个月累计涨幅(剔除最近一个月)。①档(AQR/Jegadeesh-Titman)"""
    return close.shift(21) / close.shift(252) - 1.0


def 值面板(M, name, syms):
    """★ 排序和规则共用的日频「值」面板。★ 越小越便宜的,这里给的是原值。"""
    close = M.cache.field("close", syms)
    F = M.fundamentals
    g = lambda n: F.get(n, syms).reindex(index=close.index, columns=syms)  # noqa: E731
    if name == "pe":
        e = g("eps_ttm_ps"); return close / e.where(e > 0)
    if name == "pb":
        b = g("bvps"); return close / b.where(b > 0)
    if name == "ev_ebit":
        ev = close + g("netdebt_ps"); eb = g("ebit_ttm_ps")
        return ev.where(ev > 0) / eb.where(eb > 0)
    if name == "ey":                      # ★ 原著盈利收益率:EBIT_TTM / EV(当期,非稳态)
        ev = close + g("netdebt_ps"); eb = g("ebit_ttm_ps")
        return eb.where(eb > 0) / ev.where(ev > 0)
    if name == "roc":
        return g("roc")
    if name == "pe3":
        e = g("eps3_avg_ps"); return close / e.where(e > 0)
    if name == "p_ncav":
        n = g("ncav_ps"); return close / n.where(n > 0)
    if name == "fcf_yield":
        f = g("fcf_per_share"); return f / close.replace(0.0, np.nan)
    if name == "dilution":
        return g("net_dilution_pct")
    if name == "mom_12_1":
        return _mom_12_1(close)
    if name == "eps_q_yoy":
        return g("eps_q_yoy")
    raise KeyError(f"值面板 {name} 没定义 —— ★ 没有悄悄返回 NaN")


_格雷厄姆缓存: dict = {}


def universe_rule_mask(M, rule, syms, index):
    t = rule.get("type")
    if t not in 新规则:
        return None
    p = rule.get("params", {}) or {}
    close = M.cache.field("close", syms)
    F = M.fundamentals
    g = lambda n: F.get(n, syms).reindex(index=close.index, columns=syms)  # noqa: E731

    if t == "pb_rank_bottom":
        x = 值面板(M, "pb", syms)
        return (x.notna() & (_pct(x) <= float(p.get("rank_bottom_pct", 20)) / 100)).fillna(False)

    if t == "fund_metric_threshold":
        v = 值面板(M, p["metric"], syms) if p.get("value_panel") else g(p["metric"])
        op, val = str(p.get("op", "le")), float(p["value"])
        m = {"lt": v < val, "le": v <= val, "gt": v > val, "ge": v >= val}[op]
        return (v.notna() & m).fillna(False)

    if t == "roce_rank_top_x":
        x = g("roce")
        return (x.notna() & (_pct(x) >= 1 - float(p.get("rank_top_pct", 20)) / 100)).fillna(False)

    if t == "magic_formula_available":
        # ★ 两个原著指标都算得出才进池;★★ 谁先买由排序「名次相加」决定(见 rank)
        return (值面板(M, "roc", syms).notna() & 值面板(M, "ey", syms).notna()).fillna(False)

    if t == "graham_defensive":
        # ★★ 1107 晚改成「一道一道算、算完就扔」:原写法同时攥着十几张 [日×票] 面板,
        #   并池2004 × 17 年时单这一条臂吃到 6.2GB 被 OOM 杀掉。★ 判法一字未改,只改内存用法;
        #   同一组参数的结果记下来,离场那条(同一规则)直接复用,不再算第二遍。
        key = (tuple(syms), tuple(sorted((k, str(v)) for k, v in p.items())), len(close.index))
        if key in _格雷厄姆缓存:
            return _格雷厄姆缓存[key]
        yrs = int(p.get("years", 10))
        ok = None

        def 并(x):
            nonlocal ok
            x = x.fillna(False).astype(bool)
            ok = x if ok is None else (ok & x)
            F.panel.cache_clear()

        并(g("rev_ttm") >= float(p.get("min_revenue", 0)))
        并(g("current_ratio") >= float(p.get("min_current_ratio", 2.0)))
        并(g("ltd_over_nwc") <= float(p.get("max_ltd_over_nwc", 1.0)))
        并(g("ni_pos_years") >= yrs)
        并(g("div_years") >= min(yrs, int(p.get("div_years_cap", 99))))
        e3 = g("eps3_avg_ps")
        e3_lag = F.get(f"eps3_avg_ps_lag{4 * (yrs - 3)}", syms).reindex(index=close.index, columns=syms)
        并((e3 / e3_lag.where(e3_lag > 0) - 1.0) >= float(p.get("min_growth", 1 / 3)))
        del e3_lag
        pe3 = close / e3.where(e3 > 0)
        del e3
        并(pe3 <= float(p.get("max_pe", 15.0)))
        pb = 值面板(M, "pb", syms)
        并((pb <= float(p.get("max_pb", 1.5))) | (pe3 * pb <= float(p.get("max_product", 22.5))))
        del pb, pe3
        _格雷厄姆缓存.clear()
        _格雷厄姆缓存[key] = ok
        return ok

    if t == "value_momentum_top":
        w = float(p.get("value_weight", 0.5))
        sc = 组合分(M, syms, w)
        return (sc.notna() & (_pct(sc) >= 1 - float(p.get("top_pct", 20)) / 100)).fillna(False)

    if t == "zweig_garp":
        nq = int(p.get("growth_quarters", 3))
        gq = F.get(f"zweig_growth_ok_{nq}", syms).reindex(index=close.index, columns=syms)
        pe = 值面板(M, "pe", syms)
        med = pe.median(axis=1)
        rel = pe.div(med, axis=0)
        ok = (gq >= 1.0) & (rel >= float(p.get("pe_lo_mult", 0.5))) \
            & (rel <= float(p.get("pe_hi_mult", 2.0)))
        return ok.fillna(False).astype(bool)
    return None


def 组合分(M, syms, w):
    """★ AQR 价值+动量:两个**池内分位**按权重加(★★ 是加权,不是交集 —— 卡原文)。
       价值腿用 B/M(= 1/PB)—— ★ Asness/Moskowitz/Pedersen 2013 的价值腿就是 BE/ME。"""
    pb = 值面板(M, "pb", syms)
    mom = 值面板(M, "mom_12_1", syms)
    v = _pct(-pb)                 # ★ 越便宜越高
    m = _pct(mom)
    return w * v + (1 - w) * m


# ════════════════════════════════════════════════════════════════════
# 排序(槽位不够时先买谁)—— ★ 分数越大越优先
# ════════════════════════════════════════════════════════════════════
def rank_score(M, spec, syms):
    prim = (spec or {}).get("primary") if isinstance(spec, dict) else None
    f = str((prim or {}).get("formula", ""))
    if not f.startswith("FUND:"):
        return None
    k = f[5:]
    if k == "magic":
        r1 = 值面板(M, "roc", syms).rank(axis=1, ascending=False)
        r2 = 值面板(M, "ey", syms).rank(axis=1, ascending=False)
        return -(r1 + r2)                         # ★ 名次相加,越小越好 → 取负
    if k.startswith("value_momentum_w"):
        return 组合分(M, syms, float(k[len("value_momentum_w"):]))
    low_better = {"pe", "pb", "ev_ebit", "pe3", "p_ncav", "dilution"}
    high_better = {"fcf_yield", "eps_q_yoy", "roc", "ey"}
    if k in low_better:
        return -值面板(M, k, syms)
    if k in high_better:
        return 值面板(M, k, syms)
    raise NotImplementedError(f"排序 {f} 没定义 —— ★ 没有悄悄退回默认排序")


# ════════════════════════════════════════════════════════════════════
# 离场:「不再满足就卖」—— 在检查日上,某条选股规则不成立 → 收盘判离场
# ════════════════════════════════════════════════════════════════════
def _检查日(index, check):
    s = pd.Series(index, index=index)
    if check == "daily":
        return pd.Series(True, index=index)
    key = {"monthly": s.dt.to_period("M"), "quarterly": s.dt.to_period("Q"),
           "annual": s.dt.to_period("Y")}[check]
    return key != key.shift(1)                     # ★ 每期第一个交易日


def exit_mask(M, spec, syms):
    out = None
    for rule in ((spec or {}).get("rules") or []):
        if rule.get("type") != "fund_rule_fails":
            continue
        p = rule.get("params", {}) or {}
        close = M.cache.field("close", syms)
        ok = M._universe_rule_mask(p["rule"], syms, close.index)
        chk = _检查日(close.index, str(p.get("check", "daily")))
        # ★★ 收盘价缺(停牌/退市后)那天不判 —— 和引擎「拿不到数据不凭空卖」同向
        hit = (~ok.astype(bool)) & close.notna()
        hit = hit.mul(chk.astype(bool), axis=0).astype(bool)
        out = hit if out is None else (out | hit)
    return out


# ════════════════════════════════════════════════════════════════════
# ② 茨威格大盘红绿灯(★ 利率方向 + 大盘长均线 → 红 / 黄 / 绿)
# ════════════════════════════════════════════════════════════════════
def _dtb3() -> pd.Series:
    import gzip, json
    p = os.path.join(ROOT, "market_macro_1105", "DTB3", "daily.json.gz")
    raw = json.load(gzip.open(p, "rt", encoding="utf-8"))
    rows = raw.get("data") or raw
    s = pd.Series({pd.Timestamp(r["date"]): r.get("close") for r in rows}, dtype=float)
    return s.sort_index().dropna()


def zweig_light(index, p, data) -> pd.Series:
    """★ 绿 = 利率在降 且 大盘在长均线上;黄 = 只有一条;红 = 两条都不成立。
       ★★ 开仓允许的档由 allow 决定(默认「非红」);★★★ 和引擎其它闸一样往后挪一天。"""
    r = _dtb3().reindex(index).ffill()           # ★ 节假日没有值 → 沿用上一个工作日(不是编值)
    lb = int(p.get("rate_lookback", 126))
    rate_down = (r < r.shift(lb)).fillna(False)
    b = data.load_benchmark(p.get("symbol", "SPY"))["close"].reindex(index).ffill()
    n = int(p.get("ma", 200))
    above = (b > b.rolling(n, min_periods=n).mean()).fillna(False)
    score = rate_down.astype(int) + above.astype(int)    # 0 红 / 1 黄 / 2 绿
    need = {"green": 2, "not_red": 1}[str(p.get("allow", "not_red"))]
    return score >= need


# ════════════════════════════════════════════════════════════════════
# 装上
# ════════════════════════════════════════════════════════════════════
def install() -> dict:
    global _装过
    if _装过:
        return {"★已装过": True}
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "probe", "补齐能力_1106"))
    from engine import fundamentals as F, matrices as M, data as D
    import 基本面零件_1106 as P

    上一层指标 = F.metric_quarterly

    def 指标(symbol, name):
        if name in 新指标 or name.startswith("eps3_avg_ps_lag") \
                or name.startswith("zweig_growth_ok_"):
            try:
                vals, ef = F.quarter_frame(symbol)
            except Exception:
                return pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")
            if name.startswith("eps3_avg_ps_lag"):
                k = int(name[len("eps3_avg_ps_lag"):])
                v, e = metric_quarterly(F, P, symbol, "eps3_avg_ps", vals, ef)
                return v.shift(k), e          # ★ 季度序列上滞后 k 季,生效日用本期的
            if name.startswith("zweig_growth_ok_"):
                nq = int(name[len("zweig_growth_ok_"):])
                ge, ee = metric_quarterly(F, P, symbol, "eps_q_yoy", vals, ef)
                gr, er = metric_quarterly(F, P, symbol, "rev_q_yoy", vals, ef)
                if len(ge) == 0 or len(gr) == 0:
                    return pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")
                ge, gr = ge.reindex(vals.index), gr.reindex(vals.index)
                ee = pd.to_datetime(ee.reindex(vals.index), errors="coerce")
                er = pd.to_datetime(er.reindex(vals.index), errors="coerce")
                pos = pd.concat([ge.shift(i) > 0 for i in range(nq)], axis=1).all(axis=1)
                accel = ge > ge.shift(1)
                # ★★ 卡原文「营收增长跟得上利润增长(防止只是削减成本)」——
                #   ★ 可算读法(③我们的):单季营收同比 > 0 且 ≥ 利润增速的一半
                rev_ok = (gr > 0) & (gr >= 0.5 * ge)
                avail = pd.concat([ge.shift(i).notna() for i in range(nq + 1)], axis=1).all(axis=1) \
                    & gr.notna()
                v = (pos & accel & rev_ok).astype(float).where(avail)
                return v, pd.concat([ee.reindex(vals.index), er.reindex(vals.index)],
                                    axis=1).max(axis=1)
            return metric_quarterly(F, P, symbol, name, vals, ef)
        return 上一层指标(symbol, name)          # ★★★ 认不出 → 原样转回

    F.metric_quarterly = 指标

    上一层规则 = M._universe_rule_mask

    def 规则(rule, syms, index):
        r = universe_rule_mask(M, rule, list(syms), index)
        if r is not None:
            return M._as_bool(r.reindex(index=index, columns=list(syms)).fillna(False))
        return 上一层规则(rule, syms, index)        # ★★★ 认不出 → 原样转回

    M._universe_rule_mask = 规则

    上一层排序 = M.rank_score_matrix

    def 排序(spec, symbols, cfg=None):
        r = rank_score(M, spec, list(symbols))
        if r is not None:
            return r.reindex(columns=list(symbols))
        return 上一层排序(spec, symbols, cfg)       # ★★★ 认不出 → 原样转回

    M.rank_score_matrix = 排序

    上一层离场 = M.exit_signal_matrix

    def 离场(spec, symbols):
        spec = spec or {}
        mine = [r for r in (spec.get("rules") or []) if r.get("type") == "fund_rule_fails"]
        rest = dict(spec)
        rest["rules"] = [r for r in (spec.get("rules") or []) if r.get("type") != "fund_rule_fails"]
        base = 上一层离场(rest, symbols)            # ★★★ 其余规则原样交回原函数
        if mine:
            x = exit_mask(M, {"rules": mine}, list(symbols))
            base = base | x.reindex(index=base.index, columns=base.columns).fillna(False)
        return base

    M.exit_signal_matrix = 离场

    上一层环境 = M.regime_mask

    def 环境(spec, index, chain_breadth_pct=None, chain_breadth_n=None):
        spec = spec or {}
        mine = [r for r in (spec.get("rules") or []) if r.get("type") == "zweig_light"]
        rest = dict(spec)
        rest["rules"] = [r for r in (spec.get("rules") or []) if r.get("type") != "zweig_light"]
        ok = 上一层环境(rest, index, chain_breadth_pct, chain_breadth_n)
        for r in mine:
            z = zweig_light(index, r.get("params", {}) or {}, D)
            ok = ok & z.shift(1, fill_value=False).astype(bool)   # ★ 往后挪一天,不偷看
        return ok

    M.regime_mask = 环境

    for fn in (getattr(F, "panel", None),):
        if fn is not None and hasattr(fn, "cache_clear"):
            fn.cache_clear()
    _装过 = True
    return {"★第三层装上了": True, "新指标": list(新指标), "新规则": list(新规则),
            "排序": "FUND:*", "离场": "fund_rule_fails", "环境": "zweig_light",
            "engine改动": "零"}
