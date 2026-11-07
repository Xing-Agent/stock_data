# -*- coding: utf-8 -*-
"""★★★ 自查（口径⑥：让我们好看的结果先当自己错了）—— 交互项是不是**敞口的假象**？

★★ 今天跑出来的正面结果：条件 alpha 的交互项（环境×指数日收益）
   趋势/突破两族在**两段**上都 t = 4.9 ~ 8.8（门槛 |t| > 3），震荡族两段都不显著。
   ★ 按跑前登记，这对应「**不同环境配不同策略**有实测支持」。

★★★ 但先问一句：**这会不会是机械的？**
   ★ 我们是**纯多头 + 趋势类**。SPY 在 200 日线上方时趋势向上 → 策略满仓；
     ★★ 线下时趋势向下 → 一路被止损打掉 → **趴在现金上**。
   → ★★★ 那么「线上时对大盘的 beta 更高」可能只是在说
     **「我们线上时仓位重、线下时仓位轻」** —— ★ 这是趋势策略的定义，
     不是「环境和策略匹配」的证据。
   → ★★ 所以必须把**敞口**这个解释先排掉。

★ 三件事：
  ① 直接量：线上 / 线下 的**平均敞口**各是多少。
  ② ★★★ 改成**同敞口口径**回归：`策略日收益 ~ (前一日敞口 × 指数日收益)
     + 环境 × (前一日敞口 × 指数日收益)`
     → ★ 这时交互项问的是「**每单位敞口**的 beta 在两种环境里一样不一样」，
       ★★ 敞口本身的差异已经被除掉。
  ③ 并报原版（不除敞口）做对照，两个数并排，★★★ 不许只报好看的那个。

★★ 口径：全收益（两侧同口径）· 窗口两段 · 池 并池2004 · 标签滞后 1 天 · NW 滞后阶 8。
"""
from __future__ import annotations
import io, json, os, sys

import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
os.chdir(ROOT)
import 配对与条件alpha_1107 as A                                   # noqa: E402

代表 = {"大波段": "技-1", "突破": "技-6-原著", "震荡": "技-14-原著"}
窗口 = {"B_2015到2025": ("2015-01-01", "2025-12-31"),
       "A_2004到2014": ("2004-01-02", "2014-12-31")}
OUT = os.path.join(HERE, "自查_交互项是不是敞口假象_报告_1107.json")


def 一条(label, 起, 止, ie):
    import statsmodels.api as sm
    d = A.读日序列(label)
    if d is None or "敞口" not in d.columns:
        return {"★算不了": "缺日序列或敞口列"}
    r = d["净值"].astype(float).pct_change().dropna()
    ex = d["敞口"].astype(float).shift(1)          # ★★★ 前一日敞口，不偷看今天
    共同 = r.index.intersection(ie.index).intersection(ex.dropna().index)
    y = r.reindex(共同).to_numpy(float)
    mkt = ie["指数日收益"].reindex(共同).to_numpy(float)
    on = ie["环境_线上"].reindex(共同).to_numpy().astype(float)
    e = ex.reindex(共同).to_numpy(float)

    def fit(X):
        return sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": A.NW_LAG})

    原 = fit(np.column_stack([np.ones(len(共同)), mkt, on, on * mkt]))
    同敞 = fit(np.column_stack([np.ones(len(共同)), e * mkt, on, on * e * mkt]))
    return {
        "①敞口": {"线上平均敞口": round(float(np.nanmean(e[on == 1])), 4),
                "线下平均敞口": round(float(np.nanmean(e[on == 0])), 4),
                "★★★线上−线下": round(float(np.nanmean(e[on == 1]) - np.nanmean(e[on == 0])), 4)},
        "②原版交互项(不除敞口)_NW_t": round(float(原.tvalues[3]), 3),
        "③★★★同敞口口径交互项_NW_t": round(float(同敞.tvalues[3]), 3),
        "③同敞口口径交互项_系数": round(float(同敞.params[3]), 4),
        "★★★门槛": "|t| > 3（9 次检验，HLZ 2016）",
        "★★★同敞口口径过没过": ("过" if abs(float(同敞.tvalues[3])) > 3 else "没过"),
        "n": int(len(共同)),
    }


def main() -> int:
    报 = {"★★★这一份回答什么": __doc__.strip()[:1600], "各段": {}}
    for 窗名, (起, 止) in 窗口.items():
        ie = A.取指数与环境(起, 止)
        报["各段"][窗名] = {}
        for 族, fn in 代表.items():
            lab = f"{窗名}·并池2004·{族}·{fn}·A原样"
            报["各段"][窗名][族] = 一条(lab, 起, 止, ie)
            print(f"★ {窗名} {族}: {json.dumps(报['各段'][窗名][族], ensure_ascii=False)}",
                  flush=True)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
