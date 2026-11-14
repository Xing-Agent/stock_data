#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流动性池 + 「机会集宽基」主对标线（2026-11-14 · Lin 1112 拍板《172》第 2 条）

大白话：技术面策略以后统一在「买得进卖得出的普通股」里挑票，
       这个池子本身「只买不动」的成绩，就是技术面的主对标（叫机会集宽基）。

池子规则（门槛原著没给 → 全部标「行业惯例 / 推断」，ADV20 门槛跑相邻三点）：
  进池：收盘价 >= 5 美元；20 日平均成交额 >= 门槛；已有 >= 60 个交易日的行情
  留池（缓冲带，推断）：收盘价 >= 4 美元；20 日平均成交额 >= 门槛 x 0.8
  每季度第一个交易日调一次，用前一个交易日为止的数据（不偷看当天）
  只在研发池 2224 只里建；留出池不碰。
  「普通股」：面板元数据没有证券类型这一列，这一条本脚本没法执行 —— 写进报告，不装作做了。

机会集宽基：每季调仓日等权买入全部成分，季内不动（权重随价格漂移），下季再等权。
           含分红（engine.data.total_return_daily）；取不到分红就退成价格收益并写明。
           不扣交易成本（写明：这会让对标略偏高，对我们不利的方向）。
engine/ 一个字节不改。
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
门槛三点 = {"低": 5e6, "中": 1e7, "高": 2e7}   # 行业惯例 / 推断，相邻三点
价进, 价留, 缓冲, 满天 = 5.0, 4.0, 0.8, 60


def main():
    import numpy as np
    import pandas as pd
    import 跑基本面_1106 as B
    RC, _ = B.装层()
    from engine import cache, data
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev = [s for s in hold["研发池名单"] if s in cache._PANEL["close"].columns]
    close = cache._PANEL["close"][dev].astype(float)
    vol = cache._PANEL["volume"][dev].astype(float)
    idx = close.index
    adv = (close * vol).rolling(20, min_periods=20).mean()
    bars = close.notna().cumsum()
    # 总收益
    分红口径 = "含分红"
    try:
        import 补分红_1107 as DIV
        DIV.install()
        有分红 = 0
        divs = {}
        for s_ in dev:
            d_ = data.dividends(s_)
            if len(d_):
                有分红 += 1
                divs[s_] = d_[~d_.index.duplicated()].reindex(idx).fillna(0.0)
        dv = pd.DataFrame(divs, index=idx).reindex(columns=dev).fillna(0.0)
        prev = close.shift(1)
        tr = ((close - prev + dv) / prev).replace([np.inf, -np.inf], np.nan)
        分红口径 = f"含分红（{有分红} / {len(dev)} 只有分红记录；除息日加回）"
    except Exception as e:  # 取不到就退成价格收益，写明
        分红口径 = f"价格收益（取分红失败：{type(e).__name__}: {e}）"
        tr = close.pct_change(fill_method=None)
    tr = tr.where(close.notna(), 0.0).fillna(0.0)
    pr = close.pct_change(fill_method=None).where(close.notna(), 0.0).fillna(0.0)

    perf = idx[idx >= pd.Timestamp(data.PERF_START)]
    q = pd.Series(perf.quarter, index=perf)
    调仓日 = [perf[0]] + [d for d, a, b in zip(perf[1:], q.values[1:], q.values[:-1]) if a != b]
    报告 = {"窗口": f"{perf[0].date()} → {perf[-1].date()}", "研发池只数": len(dev),
            "分红口径": 分红口径, "普通股过滤": "没做：面板元数据没有证券类型列",
            "规则": {"进池价": 价进, "留池价": 价留, "缓冲系数": 缓冲, "上市满交易日": 满天,
                     "出处": "行业惯例 / 推断（原著没给）"}, "三点": {}}
    线 = {}
    for 名, T in 门槛三点.items():
        mask = pd.DataFrame(False, index=perf, columns=dev)
        成员 = pd.Series(False, index=dev)
        eq = pd.Series(np.nan, index=perf)
        eq_p = pd.Series(np.nan, index=perf)
        v = vp = 1.0
        只数 = []
        for k, d in enumerate(调仓日):
            i = idx.get_loc(d)
            c, a, n = close.iloc[i - 1], adv.iloc[i - 1], bars.iloc[i - 1]
            进 = (c >= 价进) & (a >= T) & (n >= 满天)
            留 = 成员 & (c >= 价留) & (a >= T * 缓冲)
            成员 = (进 | 留).fillna(False)
            end = 调仓日[k + 1] if k + 1 < len(调仓日) else None
            seg = perf[(perf >= d) & ((perf < end) if end is not None else True)]
            mask.loc[seg, :] = 成员.values
            只数.append(int(成员.sum()))
            mem = 成员[成员].index
            if len(mem) == 0:
                eq.loc[seg], eq_p.loc[seg] = v, vp
                continue
            # 调仓日当天收盘等权买入：当天收益不算，季内买入不动
            for r, e, 起 in ((tr, eq, "v"), (pr, eq_p, "vp")):
                g = (1 + r.loc[seg, mem]).copy()
                g.iloc[0] = 1.0
                w = g.cumprod().mean(axis=1)
                base = v if 起 == "v" else vp
                e.loc[seg] = base * w.values
                # 下一季第一天的收益要补上（从上季末到调仓日收盘）
                if end is not None:
                    last = base * float((g.cumprod().iloc[-1] * (1 + r.loc[end, mem])).mean())
                else:
                    last = float(e.loc[seg].iloc[-1])
                if 起 == "v":
                    v = last
                else:
                    vp = last
        yrs = (perf[-1] - perf[0]).days / 365.25
        dd = float((eq / eq.cummax() - 1).min())
        ann = float(eq.iloc[-1]) ** (1 / yrs) - 1
        报告["三点"][名] = {"ADV20门槛美元": T, "调仓次数": len(调仓日),
                         "成分只数_最少": min(只数), "成分只数_中位": int(np.median(只数)),
                         "成分只数_最多": max(只数),
                         "复合年化pct": round(ann * 100, 2), "最大回撤pct": round(dd * 100, 2),
                         "卡玛": round(ann / abs(dd), 3) if dd < 0 else None,
                         "只算价格的复合年化pct": round((float(eq_p.iloc[-1]) ** (1 / yrs) - 1) * 100, 2)}
        mask.to_parquet(os.path.join(HERE, f"流动性池掩膜_{名}.parquet"))
        线[f"机会集宽基_{名}"] = eq
    pd.DataFrame(线).to_csv(os.path.join(HERE, "机会集宽基_日净值.csv"))
    io.open(os.path.join(HERE, "流动性池_报告.json"), "w", encoding="utf-8").write(
        json.dumps(报告, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(报告, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
