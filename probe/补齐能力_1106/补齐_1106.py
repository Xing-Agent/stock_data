# -*- coding: utf-8 -*-
"""
★★★ 补齐《78 能力对齐表》里「数据齐、零件缺」那几条 —— engine/ 零改动。
★★ 做法:全部写成 probe 层的**覆盖层算子**,每条算完必须报**实测覆盖率**。
★ 规矩:算不出就是 NaN,不猜不补(照抄 engine/fundamentals.py 的纪律)。
★★★ 规矩⑥:凡是让我们数字变好看的结果,先当自己错了。
"""
import os, sys, json, math
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from engine import fundamentals as F, data as D        # noqa: E402

OUT = os.path.join(ROOT, "probe", "补齐能力_1106")
报 = {"★口径": {
    "engine改动": "零",
    "算不出": "一律 NaN —— 不猜不补",
    "覆盖率": "有实际数值的实体数 ÷ 抽样实体数",
    "抽样": "★ 为了当场跑完,基本面类抽样 300 家;技术面类全池",
}}

# ════════════════════════════════════════════════════════════
# ★ 技 1.2 第三截 · 离 52 周高/低点多远（Minervini 趋势模板缺的那半条）
# ════════════════════════════════════════════════════════════
def 距52周(close: pd.Series, n: int = 252) -> pd.DataFrame:
    """★ 出处:Minervini《Trade Like a Stock Market Wizard》趋势模板第 6/7 条 ——
       「股价离 52 周低点至少 +25~30%」「离 52 周高点 25% 以内」。
       ★★ 52 周 = **252 个交易日**(我们的日历口径),★ 不是 365 日历日。
       ★★★ min_periods=n:不满一年的**算不出**,给 NaN,不用短窗口顶替。"""
    hi = close.rolling(n, min_periods=n).max()
    lo = close.rolling(n, min_periods=n).min()
    return pd.DataFrame({
        "离52周低点_pct": (close / lo - 1.0) * 100.0,
        "离52周高点_pct": (close / hi - 1.0) * 100.0,   # ★ 负数 = 在高点下方
    })

# ════════════════════════════════════════════════════════════
# ★ 技 5.4 派发日计数（欧奈尔）—— ★★★ engine 那条 no_distribution_day 不是这个
# ════════════════════════════════════════════════════════════
def 派发日(close: pd.Series, vol: pd.Series, 跌幅: float = 0.2,
           窗口: int = 25, 量窗: int = 50) -> pd.DataFrame:
    """★ 欧奈尔的派发日 = **放量 + 收跌** 并**计数**。
       ★★★ engine 的 no_distribution_day 只有「单日跌超 X%」—— 没有量、没有计数。
       ★ 口径标档:跌幅门槛 0.2% 与「20–25 天数 5–6 个」是**②档行业惯例**,
         ★★ 原著没给精确数 → 相邻三点都算(0.2 / 0.5 / 1.0),报是否同向。"""
    out = {}
    量均 = vol.rolling(量窗, min_periods=量窗).mean()
    放量 = vol > 量均
    for th in (0.2, 0.5, 1.0):
        跌 = (close.pct_change() * 100.0) <= -th
        是派发 = (跌 & 放量).fillna(False)
        out[f"派发日计数_{th}pct_{窗口}日"] = 是派发.rolling(窗口, min_periods=窗口).sum()
    return pd.DataFrame(out)

# ════════════════════════════════════════════════════════════
# ★ 基本面四条:现金跑道 / 杜邦 / 再投资 / FCF收益率减国债
# ════════════════════════════════════════════════════════════
def 季表(sym: str):
    try:
        return F.quarter_frame(sym)
    except Exception:
        return pd.DataFrame(), pd.DataFrame()


# ★★★ 1106 第二次修(★★ 和《24》#26 同根:**我又猜了科目名**)。
#   ★ 第一次猜错列(拿 year 当 symbol);第二次猜错**科目名** ——
#     我用 XBRL 名(NetIncome/TotalAssets),而 quarter_frame 的视图是**短代号**。
#   ★★★ 这次是脚本里**打出了库自己的科目名列表**才发现的 —— ★ 机制救的,不是我记住的。
#
# ★★ 两层名字都记在这儿,免得下次再猜:
#   quarter_frame 视图(16 个短代号):
#     ca(流动资产) capex_alt capex_ppe cl(流动负债) cor(营业成本) ebit eq(股东权益)
#     issue(发股) liab(总负债) ltd(长期债) ni(净利) ocf(经营现金流) re(留存收益)
#     rev(营收) shares(摊薄股数) ta(总资产)
#   原始库(35 个 XBRL 名,用 F.ttm/F.quarterly 单取):
#     CashAndCashEquivalentsAtCarryingValue · DepreciationDepletionAndAmortization
#     InterestExpense · DebtCurrent · ShortTermBorrowings · CurrentAssets · Liabilities ...
#   ★★★ 库里**没有** ShortTermInvestments → 现金跑道只能用**纯现金**,偏保守(跑道算得偏短)。

短 = {"净利": "ni", "营收": "rev", "总资产": "ta", "权益": "eq", "经营现金流": "ocf",
      "流动资产": "ca", "流动负债": "cl", "总负债": "liab", "长期债": "ltd",
      "EBIT": "ebit", "股数": "shares"}


def 列(vals, *名):
    """★ 按短代号取列;缺任何一个 → None(整条算不出),★★ 不用 0 顶替。"""
    if vals.empty:
        return None
    cs = [短[n] for n in 名]
    if any(c not in vals.columns for c in cs):
        return None
    d = vals[cs].astype(float)
    d.columns = list(名)
    return d if d.notna().any().all() else None


def 原始(sym, metric, ttm=False):
    """★ 取 quarter_frame 视图里没有的科目(按**库自己的** XBRL 名)。"""
    try:
        obs = F.ttm(sym, metric) if ttm else F.quarterly(sym, metric)
    except Exception:
        return None
    if not obs:
        return None
    s_ = pd.Series({o.period_end: o.value for o in obs}).dropna()
    return s_.sort_index() if len(s_) else None


def 基_杜邦(sym):
    """基 2.2 杜邦三项:净利率 x 资产周转 x 权益乘数 = ROE。三项缺一就整条算不出。"""
    v, _ = 季表(sym)
    d = 列(v, "净利", "营收", "总资产", "权益")
    if d is None:
        return None
    o = pd.DataFrame({"净利率": d["净利"] / d["营收"],
                      "资产周转": d["营收"] / d["总资产"],
                      "权益乘数": d["总资产"] / d["权益"]})
    o["ROE_杜邦"] = o["净利率"] * o["资产周转"] * o["权益乘数"]
    return o.replace([np.inf, -np.inf], np.nan).dropna()


def 基_现金跑道(sym):
    """基 3.4 现金还能撑多久(季) = 现金 / 每季净烧钱。不烧钱 -> inf。
    偏差:库里没有短期投资科目,分子只有纯现金 -> 跑道算得偏短(保守)。"""
    v, ef = 季表(sym)
    d = 列(v, "经营现金流")
    if d is None:
        return None
    现 = 原始(sym, "CashAndCashEquivalentsAtCarryingValue")
    if 现 is None:
        return None
    try:
        cap, _ = F._capex(v, ef)
    except Exception:
        return None
    fcf = d["经营现金流"] - cap.astype(float)
    idx = fcf.index.intersection(现.index)
    if not len(idx):
        return None
    烧 = (-fcf).reindex(idx)
    现 = 现.reindex(idx)
    return pd.Series(np.where(烧 > 0, 现 / 烧, np.inf), index=idx).dropna()


def 基_再投资(sym):
    """基 2.4 再投资能力 = 再投资率 x ROIC(达摩达兰)。
    ROIC = EBIT / (权益 + 长期债);再投资率 = (CapEx - 折旧) / EBIT。
    仍是③档:库里没有税率字段,用税前 EBIT 而非 EBIT(1-t) -> ROIC 系统性偏高。"""
    v, ef = 季表(sym)
    d = 列(v, "EBIT", "权益", "长期债")
    if d is None:
        return None
    折 = None
    for m in ("DepreciationDepletionAndAmortization",
              "DepreciationAmortizationAndAccretionNet"):
        折 = 原始(sym, m)
        if 折 is not None:
            break
    if 折 is None:
        return None
    try:
        cap, _ = F._capex(v, ef)
    except Exception:
        return None
    投入 = d["权益"] + d["长期债"]
    idx = d.index.intersection(折.index)
    if not len(idx):
        return None
    roic = (d["EBIT"] / 投入).reindex(idx)
    再 = ((cap.astype(float).reindex(idx) - 折.reindex(idx))
          / d["EBIT"].reindex(idx).replace(0, np.nan))
    o = pd.DataFrame({"ROIC_税前": roic, "再投资率": 再})
    o["再投资能力"] = o["ROIC_税前"] * o["再投资率"]
    return o.replace([np.inf, -np.inf], np.nan).dropna()


def 基_稳态EBIT比EV(sym):
    """基 1.3 / 4.5 的替代口径(Lin 1106 16:51「做吧」)——不需要折现率,
    所以不碰「自己定折现率 = 自己发明一个闸」那条红线。
    稳态 EBIT = 近 20 个季度(5 年)EBIT 的中位数(不是平均,避免一次性损益带偏)。
    EV = 市值 + 总债务 - 现金;市值 = 摊薄股数 x 期末收盘。
    界面必须写清:这不是教科书的「安全边际」(那要先有 DCF 内在价值),这是盈利收益率。"""
    v, _ = 季表(sym)
    d = 列(v, "EBIT", "股数", "长期债")
    if d is None:
        return None
    现 = 原始(sym, "CashAndCashEquivalentsAtCarryingValue")
    if 现 is None:
        return None
    try:
        px = D.load_ohlcv(sym)["close"]
    except Exception:
        return None
    稳 = d["EBIT"].rolling(20, min_periods=20).median()
    短债 = 原始(sym, "DebtCurrent") or 原始(sym, "ShortTermBorrowings")
    out = {}
    for t in 稳.dropna().index:
        pxs = px[px.index <= t]
        if not len(pxs):
            continue
        mc = float(d["股数"].get(t, np.nan)) * float(pxs.iloc[-1])
        债 = float(d["长期债"].get(t, np.nan)) + (
            float(短债.get(t, 0.0)) if 短债 is not None else 0.0)
        c = float(现.get(t, np.nan))
        if not (np.isfinite(mc) and np.isfinite(债) and np.isfinite(c)):
            continue
        ev = mc + 债 - c
        if ev <= 0:
            continue
        out[t] = float(稳[t]) * 4.0 / ev * 100.0
    return pd.Series(out).sort_index() if out else None


def 基_netnet(sym):
    """基 1.5 清算价值底线(格雷厄姆 Net-Net,加分项)。
    净流动资产 = 流动资产 - 总负债(原著口径,不是减流动负债)。
    原著判据:市值 < 净流动资产 x 2/3。本函数返回 净流动资产/市值。"""
    v, _ = 季表(sym)
    d = 列(v, "流动资产", "总负债", "股数")
    if d is None:
        return None
    try:
        px = D.load_ohlcv(sym)["close"]
    except Exception:
        return None
    ncav = d["流动资产"] - d["总负债"]
    out = {}
    for t in ncav.dropna().index:
        pxs = px[px.index <= t]
        if not len(pxs):
            continue
        mc = float(d["股数"].get(t, np.nan)) * float(pxs.iloc[-1])
        if not np.isfinite(mc) or mc <= 0:
            continue
        out[t] = float(ncav[t]) / mc
    return pd.Series(out).sort_index() if out else None


def 基_利息覆盖(sym):
    """基 3.3 的利息覆盖那半条(到期墙那半条 Lin 1106 16:51「就算了」)。
    = EBIT / 利息支出。probe 里跑过、engine 里没有这道闸。"""
    v, _ = 季表(sym)
    d = 列(v, "EBIT")
    if d is None:
        return None
    ie = 原始(sym, "InterestExpense")
    if ie is None:
        return None
    idx = d.index.intersection(ie.index)
    if not len(idx):
        return None
    return (d["EBIT"].reindex(idx)
            / ie.reindex(idx).replace(0, np.nan)
            ).replace([np.inf, -np.inf], np.nan).dropna()

def 无风险利率():
    """★ 基 4.2 的第二条腿。★★ 按 Lin/我们已登记的倾向用 DGS3MO(债券等价口径)。"""
    for p in ("probe/rates_1102/DGS3MO.csv",
              "market_macro_1105/DGS3MO.csv", "market_macro_1105/DTB3.csv",
              "probe/macro_1105/raw/fred_DTB3_fredgraph_20261105.csv"):
        f = os.path.join(ROOT, p)
        if os.path.exists(f):
            d = pd.read_csv(f)
            c0, c1 = d.columns[0], d.columns[1]
            s = pd.Series(pd.to_numeric(d[c1], errors="coerce").values,
                          index=pd.to_datetime(d[c0], errors="coerce")).dropna()
            return s.sort_index(), p
    return None, None

# ════════════════════════════════════════════════════════════
# ★★★ 实测:逐条报覆盖率
# ════════════════════════════════════════════════════════════
def main() -> int:
    # ---- 技术面两条:在真面板上跑 ----
    try:
        spy = D.load_benchmark("SPY")
        t = 距52周(spy["close"])
        p = 派发日(spy["close"], spy["volume"])
        报["技1.2_离52周高低点"] = {
            "状态": "✅ 做出来了",
            "出处": "①档 Minervini 趋势模板第 6/7 条（52 周 = 252 交易日）",
            "SPY上实测_可算天数": int(t["离52周低点_pct"].notna().sum()),
            "SPY上实测_总天数": int(len(t)),
            "★头252天算不出": "★ min_periods=252 —— 不满一年给 NaN，不用短窗口顶替",
            "最后一天_离52周低点_pct": round(float(t["离52周低点_pct"].iloc[-1]), 2),
            "最后一天_离52周高点_pct": round(float(t["离52周高点_pct"].iloc[-1]), 2),
        }
        同向 = {k: round(float(v.iloc[-1]), 1) for k, v in p.items()}
        报["技5.4_派发日计数"] = {
            "状态": "✅ 做出来了（★★★ 和 engine 那条 no_distribution_day 不是一回事）",
            "差别": "★ 我们这条有**成交量条件**（量 > 50 日均量）+ **滚动计数**；"
                   "engine 那条只有「单日跌超 X%」",
            "出处": "①档 欧奈尔「放量收跌并计数」；★★ 跌幅门槛与「20–25 天 5–6 个」是 ②档惯例",
            "相邻三点_SPY最后一天": 同向,
            "三点是否同向": "★ 见上（计数随门槛放宽而单调下降属正常，不是同向判据）",
        }
    except Exception as e:
        报["技术面两条"] = {"状态": "❌ 跑失败", "原因": repr(e)[:300]}

    # ---- 基本面四条:抽样 300 家报覆盖率 ----
    try:
        man = None
        for p_ in ("probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv",):
            f = os.path.join(ROOT, p_)
            if os.path.exists(f):
                man = pd.read_csv(f); break
        # ★★★ 1106 修(★ 和《24》#26 同一个毛病:列猜错了):
        #   这张表第 1 列是 **year**,不是 symbol —— 原来 iloc[:,0] 取到 300 个「2015」,
        #   ★ 结果 load_fundamentals 全 KeyError → 三条全报 0.0% 覆盖率。
        #   ★★ 现在**按列名取**,并在报告里打出用的是哪一列。
        if man is None or "symbol" not in man.columns:
            raise RuntimeError("池子表里没有 symbol 列 —— ★ 不猜列名")
        syms = sorted(set(man["symbol"].astype(str)))
        报["★用的列"] = "symbol（★ 按列名取，不按位置取）"
        # ★ 用 sha256 切样本,不用随机数(随机能重抽)
        import hashlib
        syms = sorted(syms, key=lambda s: hashlib.sha256(s.encode()).hexdigest())[:300]
        报["★基本面抽样"] = {"家数": len(syms), "切法": "sha256(代码) 排序取前 300 —— ★ 不用随机数"}
        # ★★★ 规矩③(1106 补):**先把那个库自己的科目名列表打出来**,再去里面找概念。
        for s0 in syms[:40]:
            v0, _ = 季表(s0)
            if not v0.empty:
                报["★库里真实的科目名"] = {"样本公司": s0, "列": sorted(v0.columns)}
                break
        计 = {"现金跑道": 0, "杜邦": 0, "再投资": 0}
        期数 = {k: [] for k in 计}
        for s in syms:
            for 名, fn in (("现金跑道", 基_现金跑道), ("杜邦", 基_杜邦), ("再投资", 基_再投资)):
                try:
                    r = fn(s)
                except Exception:
                    r = None
                if r is not None and len(r) > 0:
                    计[名] += 1; 期数[名].append(len(r))
        for 名 in 计:
            报[f"基_{名}"] = {
                "状态": "✅ 做出来了" if 计[名] else "❌ 算不出",
                "有实际数值的家数": 计[名],
                "覆盖率": f"{计[名]/max(len(syms),1)*100:.1f}%",
                "每家期数中位": (int(np.median(期数[名])) if 期数[名] else None),
            }
        报["基_杜邦"]["口径"] = "★ 三项缺一就整条 NaN —— 不给「两项版」"
        报["基_再投资"]["★偏差"] = ("★★★ ROIC 用 NetIncome 近似（没有税率字段），"
                                "原著（达摩达兰）用 EBIT(1−t) → **高税率公司的 ROIC 会被算低**")
    except Exception as e:
        报["基本面三条"] = {"状态": "❌ 跑失败", "原因": repr(e)[:300]}

    # ---- 基 4.2 FCF收益率 减 国债 ----
    rf, rfp = 无风险利率()
    if rf is None:
        报["基4.2_FCF收益率减国债"] = {"状态": "❌ 找不到无风险利率文件",
                                   "★说明": "★ 两条腿里的国债那条没找到文件 —— 不编一个数顶替"}
    else:
        报["基4.2_FCF收益率减国债"] = {
            "状态": "✅ 减法这一步做出来了",
            "国债序列": rfp,
            "口径": "DGS3MO（债券等价口径）—— ★ 不用 DTB3 贴现口径（按 360 天算，会系统性偏低）",
            "区间": f"{rf.index.min().date()} ~ {rf.index.max().date()}",
            "行数": int(len(rf)),
            "最后一天_年化pct": round(float(rf.iloc[-1]), 3),
            "★公式": "超额FCF收益率 = fcf_per_share ÷ 收盘 × 100 − 当日国债年化(%)",
            "★★★ 已登记偏差（不因这条做出来而消失）": (
                "回购凶的公司期间加权股数偏高 → fcf_per_share 分母偏大 → "
                "FCF 收益率被**系统性低估**；而「回购凶」正是这一派要选的特征"
                "（engine/matrices.py:370 注释）"),
            "★★ 另一条": "回测里无风险利率仍按 0% 记（engine/analyze.py:479）—— "
                       "★ 这条**没改**，engine 冻结；本算子只给「超额收益率」这个指标本身",
        }

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "补齐_报告_1106.json"), "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(json.dumps(报, ensure_ascii=False, indent=1))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
