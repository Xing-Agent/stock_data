# -*- coding: utf-8 -*-
"""
★★★ 环境分档 —— 一笔交易都不改,只把已跑出的成绩按「进场那天的环境」切开看。
★ Lin 1105 18:14 拍板:先切开看;并补充「环境不只是大盘,还有行业、股票大小」。

★★ 四个轴(★ 第四个有坑,见下):
   ① 大盘方向  SPY 对 200 日线(上方/下方)
   ② 大盘波动  SPY 20 日已实现波动率,在过去 252 日里的百分位(低/中/高)
   ③ 股票大小  流水自带 liquidity_tier(★ 进场当天算的,时点干净)
   ④ 行业      ⚠ 只有今天的快照(non-PIT)+ 只覆盖 300 只 → **只看,不当闸,必须标明**

★★★ 纪律:
   · 每格必报笔数;笔数 < 30 的格子**不给结论**,只给数(规矩⑥:先问判据分辨力)
   · 「算不出」和「成绩差」分开记,不混成一个数
   · 不写「建议用在哪个行业/哪种环境」,只给数字 —— 判断留给 Lin 和用户

★★★ 1106 修 Bug ①(和另两个脚本同一个 bug):
   45 份 REAL__*.csv 里按内容 sha256 只有 32 份是唯一的(11 组是一模一样的副本),
   原来 `glob` 一遍全吃进去 → 同一条链被当成两条、笔数被重复计入。
   ★ 现在 import `去重流水_1106` 按内容去重,★★ 去重全过程写进 json 口径节,不许静默去重。
"""
from __future__ import annotations
import io, json, os, re, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import data as edata            # noqa: E402
from 去重流水_1106 import 去重后的流水文件, 去重报告   # noqa: E402

LED = "probe/friction_rerun_1104/ledgers_1104"
OUT = "probe/环境分档_1105"
MIN_N = 30                                   # ★ 低于这个笔数不给结论


def 大盘轴() -> pd.DataFrame:
    """★ 用 SPY 造两条环境轴,★★ 全部只用当天及以前的数据(因果)。"""
    spy = edata.load_benchmark("SPY")
    col = "close" if "close" in spy.columns else spy.columns[-1]
    px = spy[col].astype(float)

    ma200 = px.rolling(200, min_periods=200).mean()
    方向 = pd.Series(np.where(px > ma200, "大盘在200日线上方", "大盘在200日线下方"),
                     index=px.index)
    方向[ma200.isna()] = None                 # ★ 预热期不判,记成算不出

    ret = np.log(px).diff()
    vol20 = ret.rolling(20, min_periods=20).std() * np.sqrt(252)
    # ★ 百分位只看过去 252 天(含当天),★★ 不用全样本排名 —— 那是偷看未来
    pct = vol20.rolling(252, min_periods=252).rank(pct=True)
    波动 = pd.Series(np.where(pct.isna(), None,
                     np.where(pct <= 1/3, "低波动",
                     np.where(pct <= 2/3, "中波动", "高波动"))), index=px.index)
    return pd.DataFrame({"方向": 方向, "波动": 波动})


def 行业表() -> dict:
    f = "pilot_300/sector_classification_current_non_pit.csv"
    if not os.path.exists(f):
        return {}
    d = pd.read_csv(f)
    c0 = d.columns[0]
    sc = next((c for c in d.columns if "sector" in c.lower()), None)
    return {} if sc is None else dict(zip(d[c0].astype(str), d[sc].astype(str)))


def 格子(g: pd.DataFrame) -> dict:
    """★ 一个格子的成绩。★★ 笔数不够就只给数、不给结论。"""
    r = g["r_multiple_net"].dropna().astype(float)
    n = len(r)
    if n == 0:
        return {"笔数": 0, "★状态": "算不出(这一格没有交易)"}
    mean = float(r.mean())
    se = float(r.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    out = {
        "笔数": n,
        "每笔净R": round(mean, 4),
        "标准误": (round(se, 4) if np.isfinite(se) else None),
        "胜率": round(float((r > 0).mean()), 4),
        "净盈亏美元": round(float(g["net_pnl"].sum()), 2),
        "中位持有天数": (float(g["holding_days"].median())
                         if "holding_days" in g else None),
    }
    if n < MIN_N:
        out["★状态"] = f"笔数不足{MIN_N}(只给数,不给结论)"
    elif np.isfinite(se) and abs(mean) <= 2 * se:
        out["★状态"] = "和0分不开(小于噪声)"
    else:
        out["★状态"] = "赚" if mean > 0 else "亏"
    return out


def main() -> int:
    env = 大盘轴()
    sec = 行业表()
    报告 = 去重报告(LED)                     # ★★★ Bug ①:去重,且全过程记进 json
    files = 去重后的流水文件(LED)
    结果, 跳过 = {}, []
    for f in files:
        链 = os.path.basename(f)[len("REAL__"):-len(".csv")]
        d = pd.read_csv(f)
        if "entry_date" not in d or "r_multiple_net" not in d:
            跳过.append({"链": 链, "原因": "流水缺 entry_date 或 r_multiple_net"})
            continue
        d["entry_date"] = pd.to_datetime(d["entry_date"])
        d = d.join(env, on="entry_date")
        if sec:
            d["行业"] = d["symbol"].astype(str).map(sec)
        rec = {"总笔数": len(d), "全样本": 格子(d), "分档": {}}
        for 轴 in ["方向", "波动", "liquidity_tier"] + (["行业"] if sec else []):
            if 轴 not in d.columns:
                continue
            cells, na = {}, int(d[轴].isna().sum())
            for k, g in d.groupby(d[轴].astype("object"), dropna=True):
                cells[str(k)] = 格子(g)
            rec["分档"][轴] = {"各档": cells, "★这一轴算不出的笔数": na}
        结果[链] = rec

    os.makedirs(OUT, exist_ok=True)
    payload = {
        "口径": {
            "基线": "probe/friction_rerun_1104 (摩擦口径统一后 + engine 修完)",
            "成绩字段": "r_multiple_net(每笔净 R)",
            "★改没改交易": "没有。一笔都没重跑,只是按进场日打环境标签后切开看。",
            "大盘方向": "SPY 收盘 vs 200 日均线(min_periods=200,预热期记算不出)",
            "大盘波动": "SPY 20 日已实现波动率 → 在过去 252 日内的百分位,1/3 与 2/3 分三档"
                        "(★ 滚动排名,不用全样本排名)",
            "股票大小": "流水自带 liquidity_tier(★ 进场当天算的,时点干净)",
            "行业": ("⚠ sector_classification_current_non_pit.csv —— "
                     "**今天的快照,不是当年的**,且只覆盖 pilot_300。"
                     "★★★ 只用于切开看,不得当闸门(engine matrices.py:352 已硬挡)"),
            "不给结论的门槛": f"笔数 < {MIN_N} 的格子只给数",
            "和0分不开的判据": "|每笔净R| <= 2 × 标准误",
            "★★★1106修的bug": "Bug ①:45 份 REAL__*.csv 里按内容 sha256 只有 32 份唯一"
                               "(11 组重复副本),原来全吃进去 → 笔数被重复计入。"
                               "★ 现在按内容去重,明细见「★流水去重」。",
            "★流水去重": 报告,
        },
        "链数": len(结果), "跳过": 跳过, "逐链": 结果,
    }
    p = os.path.join(OUT, "环境分档_1105.json")
    io.open(p, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"★ 写到 {p} · {len(结果)} 条链 · 跳过 {len(跳过)} · "
          f"流水 {报告['原始份数']} 份 → 去重后 {报告['去重后份数']} 份"
          f"(丢掉 {报告['被丢掉的份数']} 份 / {报告['重复组数']} 组重复)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
