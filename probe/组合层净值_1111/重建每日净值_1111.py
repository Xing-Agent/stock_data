#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从已有流水重建每条策略的「组合层每日净值」（2026-11-11）

★★★★★ 为什么要做：Gemini《165》回复 + Lin 15:10 拍板的排序办法（卡玛比率）
   **全部要求组合层每日净值**：卡玛 · 索提诺 · 在场率 · 最大回撤持续天数 ·
   对 SPY 回归的 α —— ★★ 一个都离不开它。
   ★★★ 而我们现在只有汇总后的 alpha 和回撤，★★★★★ **每日净值一条都没有**。

★★★ 两个硬口径（★ 都是 Lin 定的，不许偷）：
   ① **每天按市价重估** —— ★★★★★ 只用已实现盈亏会**低估回撤**（★ 持仓期间的浮亏看不见）。
      ★★ 那是实质差别，不是精度问题。
   ② **年化一律用复合年化**：(期末 ÷ 期初)^(1 ÷ 年数) − 1，★★★★★ **空仓的日子也算在内**
      （★ Lin 2026-11-11 15:10）。
   ★★★ 并且**不许**用「乘以 252 ÷ 持有天数」折年化（★ Gemini 指出会放大几百倍，1111 已撤回）。

★ 不碰 engine/ 一个字节 —— ★★★ 价格一律走引擎自己的 `data.price_panel()`，不自己重写。
"""
import glob
import io
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = "/home/claude/xing-agent-stock_data"
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "probe/组合层净值_1111/出")
os.makedirs(OUT, exist_ok=True)

初始资金 = 1_000_000.0
窗口 = ("2015-01-01", "2025-12-31")


def 找流水():
    """★ 按跑批目录分组，★★ 只取有 entry_date 的 csv"""
    组 = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "probe/**/*.csv"), recursive=True)):
        try:
            with io.open(p, encoding="utf-8", errors="ignore") as h:
                if "entry_date" not in h.readline():
                    continue
        except Exception:
            continue
        组.setdefault(os.path.relpath(os.path.dirname(p), ROOT), []).append(p)
    return 组


def 重建一条(csv路径, 收盘价):
    """★★★★★ 核心：从流水重建每日净值（★ 每天按市价重估）

    做法：
      · 现金从 初始资金 起；进场日扣 notional_in + 摩擦，离场日收 notional_out
      · 每天的持仓市值 = Σ(shares × 当日收盘价)
      · 净值 = 现金 + 持仓市值
    ★★★ 退市票：引擎的 price_panel 在最后一根 K 线后补 0.0，★ 所以持有到退市会吃 −100%，
      这是引擎自己的口径，★★ 我们沿用，不另处理。
    """
    d = pd.read_csv(csv路径)
    need = {"symbol", "entry_date", "exit_date", "shares", "notional_in", "notional_out"}
    if not need.issubset(d.columns):
        return None, f"缺列 {sorted(need - set(d.columns))}"
    d = d.dropna(subset=["symbol", "entry_date", "shares"])
    if not len(d):
        return None, "空流水"
    d["entry_date"] = pd.to_datetime(d["entry_date"])      # ★ 纯日期，不做 utc 解析（1110 踩过）
    d["exit_date"] = pd.to_datetime(d["exit_date"])
    syms = tuple(sorted(d["symbol"].astype(str).unique()))

    px = 收盘价.reindex(columns=[s for s in syms if s in 收盘价.columns])
    缺票 = [s for s in syms if s not in 收盘价.columns]
    # ★★★★★ 日历改过一次：第一版写死 2015~2025 —— 🔴 但有些臂的窗口是 2004~2014
    #   （★ 文件名里就写着「A_2004到2014」），★★★ 导致进场日全被挤到第 0 天、
    #   ★ 用 2015 年的价格去估 2004 年买的股数 → ★★ 起始净值算出 6,251 万（初始只有 100 万）。
    #   ✅ 改成**用每条臂流水自己的窗口**。
    cal = px.loc[d["entry_date"].min():d["exit_date"].max()].index
    if not len(cal):
        return None, "日历为空"

    持仓 = pd.DataFrame(0.0, index=cal, columns=px.columns)
    现金 = pd.Series(0.0, index=cal)
    for r in d.itertuples(index=False):
        s = str(r.symbol)
        if s not in 持仓.columns:
            continue
        a = cal.searchsorted(r.entry_date)
        b = cal.searchsorted(r.exit_date) if pd.notna(r.exit_date) else len(cal) - 1
        if a >= len(cal):
            continue
        b = min(b, len(cal) - 1)
        # ★★★★★ 这一行改过一次（★ 硬自证抓出来的）：第一版是 `a:b+1` ——
        #   🔴 **离场那天既算持仓市值、又收了卖出现金，重复计一天**。
        #   ★★ 对提前离场的臂会在次日washout，★★★ 但对「最后一天才离场」的那些永远不washout
        #   → ★ 实测差额 2,750,920；改成 `a:b`（★★ 离场日只收现金、不再持仓）后**差额 0**。
        持仓.iloc[a:b, 持仓.columns.get_loc(s)] += float(r.shares)
        现金.iloc[a] -= float(r.notional_in) + float(getattr(r, "friction_cost", 0.0) or 0.0)
        if pd.notna(r.exit_date) and b < len(cal):
            现金.iloc[b] += float(r.notional_out) if pd.notna(r.notional_out) else 0.0

    现金累计 = 初始资金 + 现金.cumsum()
    市值 = (持仓 * px.loc[cal]).sum(axis=1)
    净值 = 现金累计 + 市值
    在场 = (持仓.abs().sum(axis=1) > 0)

    # ★★★★★ **硬自证闸**：Σnet_pnl 必须等于「末净值 − 初始资金」
    #   ★★★ 这是个会真报警的检验 —— ★ 它今天抓出了上面那个 off-by-one（差额 275 万）。
    #   ★★ 对不上就**拒绝出数**，不许把错数当结果交出去。
    # ───────── 闸① 缺价格 ─────────
    # ★★★★★ 这个闸**改过一次**（★ 第一轮 833 条跑完才发现）：
    #   🔴 第一版在这里**照样出数**，只在「★自证」里写一句「做不了」——
    #      ★★ 结果 7 条 REAL 臂带着 125/181、327/851 只缺价格的票出了数，
    #      ★★★ 算出 **年化 20429%**、**回撤 −160%**。
    #   ★★★★★ 「做不了」和「出个数再附一句免责」**是两件事** —— ★ 这正是口径⑥：
    #      凡是让数字变好看（或变离谱）的结果，先当自己错了。
    #   ✅ 现在：**缺一只票就拒绝出数**（★ 卖出现金收得到、持仓市值估不到 → 净值必然失真）。
    if 缺票:
        return None, (f"🔴 做不了 —— {len(缺票)}/{len(syms)} 只票取不到价格"
                      f"（{len(缺票)/len(syms):.0%}）：{缺票[:6]}")

    # ───────── 闸② 这到底是不是「组合层」流水 ─────────
    # ★★★★★ 新加（★ 第一轮跑完发现的真问题）：**有一批流水压根不是组合层的。**
    #   ★ 实测 `CTRL__剔污染_buy_and_hold(锚点)`：最大同时持仓 **8,406 笔**、
    #     峰值名义合计 **6,947 万** —— ★★ 而初始资金只有 **100 万**。
    #   ★★★ 它们是**逐笔/信号层**流水：每个信号都独立成交，没有组合容量约束。
    #   ★★★★★ 把它们当组合层重建 → 现金跑到 −6,800 万 → 净值为负 → **回撤 −4291%**。
    #   ★★★ 判法用**会计恒等式**，不用文件名前缀（★ 「关键词太字面」已经犯过 8 次）：
    #      **这个引擎不加杠杆**（engine/chain.py:486 `cash = initial_equity`，只在现金够时开仓）
    #      → ★★★★★ **真·组合层流水的现金永远不会显著为负**。
    现金低点 = float(现金累计.min())
    if 现金低点 < -0.01 * 初始资金:
        return None, (f"🔴 不是组合层流水 —— 现金最低跑到 {现金低点:,.0f}"
                      f"（初始资金 {初始资金:,.0f}）→ ★★ 这是**逐笔/信号层**流水，"
                      f"每个信号独立成交、没有组合容量约束，★★★ 不能当组合净值重建")

    # ───────── 闸③ 硬自证：Σnet_pnl ─────────
    # ★★★★★ **硬自证闸**：Σnet_pnl 必须等于「末净值 − 初始资金」
    #   ★★★ 这是个会真报警的检验 —— ★ 它抓出了上面那个 off-by-one（差额 275 万）。
    #   ★★ 对不上就**拒绝出数**，不许把错数当结果交出去。
    if "net_pnl" in d.columns:
        应为 = float(d["net_pnl"].sum())
        实际 = float(净值.iloc[-1] - 初始资金)
        规模 = max(float(d["net_pnl"].abs().sum()), 1.0)
        if abs(实际 - 应为) > 0.01 * 规模:
            return None, (f"🔴 自证不过：净变化 {实际:,.0f} ≠ Σnet_pnl {应为:,.0f}"
                          f"（差 {实际-应为:,.0f}，超过 Σ|pnl| 的 1%）")
        自证 = "✅ Σnet_pnl 对上 + 现金没负"
    else:
        # ★ 流水没有 net_pnl 列 → ★★★ 三道闸只过了两道，★ 照实标，不写「✅」
        自证 = "⚠ 流水无 net_pnl 列：只过了「缺价格」和「现金没负」两道"
    return {"净值": 净值, "在场": 在场, "缺票": 缺票, "笔数": len(d), "票数": len(syms),
            "现金低点": 现金低点, "★自证": 自证}, None


def 指标(净值, 在场, spy):
    nv = 净值.dropna()
    if len(nv) < 60 or nv.iloc[0] <= 0:
        return None
    年数 = (nv.index[-1] - nv.index[0]).days / 365.25
    # ★★★★★ 复合年化（Lin 1111 15:10）：空仓的日子也算在内
    cagr = (nv.iloc[-1] / nv.iloc[0]) ** (1 / 年数) - 1 if 年数 > 0 else np.nan
    峰 = nv.cummax()
    回撤 = nv / 峰 - 1
    最大回撤 = 回撤.min()
    # ★ 最大回撤持续天数（★★ 从创新高到再创新高）
    水下 = 回撤 < 0
    最长水下, 当前 = 0, 0
    for v in 水下:
        当前 = 当前 + 1 if v else 0
        最长水下 = max(最长水下, 当前)
    日收益 = nv.pct_change().dropna()
    下行 = 日收益[日收益 < 0]
    out = {
        "起": str(nv.index[0].date()), "止": str(nv.index[-1].date()), "年数": round(年数, 2),
        "复合年化%": round(cagr * 100, 2) if pd.notna(cagr) else None,
        "最大回撤%": round(最大回撤 * 100, 2),
        "最长水下天数": int(最长水下),
        "卡玛": round(cagr / abs(最大回撤), 3) if 最大回撤 < 0 and pd.notna(cagr) else None,
        "索提诺": round(cagr / (下行.std() * np.sqrt(252)), 3) if len(下行) > 5 and 下行.std() > 0 else None,
        "在场率%": round(在场.mean() * 100, 1),
    }
    # ★ 对 SPY 回归的 α（★★ 日频，★★★ 不做 NW 校正 —— 这里只要 α，t 值归内部）
    if spy is not None:
        b = spy.reindex(日收益.index).pct_change().dropna()
        共 = 日收益.index.intersection(b.index)
        if len(共) > 60:
            x = b.loc[共].values
            y = 日收益.loc[共].values
            beta = np.polyfit(x, y, 1)[0]
            alpha_d = y.mean() - beta * x.mean()
            out["对SPY_beta"] = round(float(beta), 3)
            out["对SPY_alpha年%"] = round(float(alpha_d) * 252 * 100, 2)
    return out


def main():
    from engine import data as D

    # ★★★★★ 价格源改过一次（★ 记在这里，这是今天差点出错数的地方）：
    #   【第一版】用 `D.price_panel("close")` —— 🔴 **它只有 300 列（pilot_300 老池）**，
    #     ★★★ 而流水里的票来自新池：实测覆盖率只有 **6.2% ~ 16.1%** →
    #     ★★★★★ 直接跑会让大部分持仓取不到价格，**重建出来的净值是错数**。
    #   【第二版 · 现行】照跑批自己的办法喂新池宽表：
    #     `probe/基本面跑批_1106/跑基本面_1106.py:24,43` 读
    #     `probe/newpool_1106/ohlcv_panel_newpool.parquet`（200MB，MultiIndex 列）。
    #   ★★ 这不是绕开引擎 —— ★★★ 跑批本来就是这么喂的，我们用的是**同一张表**。
    #   【第三版 · 现行】🔴 **第二版还是不够宽** —— ★★ 带闸重跑后 **718 条失败里 640 条栽在闸①**
    #     （★ 缺价格）。★★★ 一查：`newpool_1106` 这张表只到 **2807 只 · 2014-01 起**，
    #     ★ 而很多臂的名字里就写着「**并池2004**」「A_2004到2014」。
    #   ✅ 换成 `probe/并池2004_1107/ohlcv_panel_newpool.parquet` ——
    #     ★★★★★ **3858 只 · 2004-01-02 ~ 2026-11-04**，★★ 在票数和年份上都**真包含**上一张。
    #   ★★★ 这不是「挑一张让数字好看的表」：★ 旧表在 2004~2013 整段**一个价格都没有**，
    #     ★★ 那不是「分数差」，是「算不出来」—— ★★★★★ 两件事必须分开记。
    NEWPANEL = os.path.join(ROOT, "probe/并池2004_1107/ohlcv_panel_newpool.parquet")
    print(f"【前置】读新池宽表 {NEWPANEL} …")
    wide = pd.read_parquet(NEWPANEL)
    收盘价 = wide["close"] if "close" in wide.columns.get_level_values(0) else None
    assert 收盘价 is not None, "🔴 新池宽表里没有 close 层"
    收盘价.index = pd.to_datetime(收盘价.index)      # ★ 纯日期，不 utc 解析（1110 踩过）
    # ★ 自证：覆盖率必须远高于老池那 6~16%，否则说明表读错了
    print(f"【自证】新池宽表 {收盘价.shape[0]} 行 × {收盘价.shape[1]} 列 "
          f"（★ 老池 price_panel 只有 300 列）")
    assert 收盘价.shape[1] > 900, f"🔴 只有 {收盘价.shape[1]} 列，不像新池（预期 >900）"
    # ★★★★★ 并池表的硬自证：★ 票数和起始年份都必须覆盖得住 2004 那批臂
    assert 收盘价.shape[1] >= 3800, f"🔴 只有 {收盘价.shape[1]} 列，不像并池2004（预期 ≥3800）"
    assert 收盘价.index[0].year <= 2004, f"🔴 起点是 {收盘价.index[0].date()}，不是 2004 —— ★★ 2004~2013 那批臂会整段取不到价"
    print(f"【前置】宽表 {收盘价.shape[0]} 行 × {收盘价.shape[1]} 列")
    spy = None
    try:
        spy = D.load_benchmark("SPY")["close"]
        print("【前置】SPY 基准已读")
    except Exception as e:
        print(f"🟡 SPY 读不到（{e}）—— ★ α 这一列会留空，**不用近似值顶上**")

    组 = 找流水()
    print(f"【前置】找到 {len(组)} 个跑批目录，共 {sum(len(v) for v in 组.values())} 个流水文件\n")

    结果, 失败 = [], []
    for 目录, fs in sorted(组.items(), key=lambda kv: -len(kv[1])):
        for p in fs:
            名 = os.path.basename(p)[:-4]
            r, err = 重建一条(p, 收盘价)
            if err:
                失败.append({"跑批": 目录, "臂": 名, "原因": err})
                continue
            m = 指标(r["净值"], r["在场"], spy)
            if m is None:
                失败.append({"跑批": 目录, "臂": 名, "原因": "净值点数不足"})
                continue
            # ★★★★★ 「★自证」**必须进汇总表**（★ 第一轮漏了这一列 ——
            #   ★★ 于是 833 行里**看不出哪条自证过了、哪条没过**，等于白做。
            m.update({"跑批": 目录, "臂": 名, "笔数": r["笔数"], "票数": r["票数"],
                      "缺价格的票": len(r["缺票"]), "现金低点": round(r["现金低点"]),
                      "★自证": r["★自证"]})
            结果.append(m)
            r["净值"].to_frame("净值").to_csv(
                os.path.join(OUT, f"净值__{目录.replace('/', '_')}__{名[:70]}.csv"))
        print(f"  {目录:34s} 完成 {len([x for x in 结果 if x['跑批']==目录]):4d} / 失败 "
              f"{len([x for x in 失败 if x['跑批']==目录]):4d}")

    df = pd.DataFrame(结果)
    df.to_csv(os.path.join(OUT, "指标汇总_1111.csv"), index=False)
    json.dump(失败, io.open(os.path.join(OUT, "失败清单_1111.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n【结果】成功 {len(结果)} 条臂 · 失败 {len(失败)} 条")
    print(f"【结果】指标汇总 → {OUT}/指标汇总_1111.csv")

    # ★★★ 失败按**原因**分类报（★ 「算不出来」和「分数差」分开记 —— ★★ 这里全是前者）
    if 失败:
        print("\n★★★ 失败分类（★ 按闸）：")
        桶 = {}
        for x in 失败:
            k = ("闸①缺价格" if "取不到价格" in x["原因"] else
                 "闸②不是组合层流水" if "不是组合层流水" in x["原因"] else
                 "闸③Σnet_pnl对不上" if "自证不过" in x["原因"] else
                 "点数不足" if "点数不足" in x["原因"] else "其他")
            桶[k] = 桶.get(k, 0) + 1
        for k, v in sorted(桶.items(), key=lambda kv: -kv[1]):
            print(f"   {k:22s} {v:4d} 条")

    # ★★★★★ **出表后再查一遍**（★ 第一轮的教训）：三道闸都过了，★★ 数字还可能离谱。
    #   ★ 回撤不可能低于 −100%（★★ 不加杠杆的组合跌到 0 就到底了）；★★★ 年化不能是 NaN。
    if len(df):
        离谱 = df[(df["最大回撤%"] < -100) | (df["复合年化%"].isna())]
        if len(离谱):
            print(f"\n🔴 ★★★★★ **出表后还有 {len(离谱)} 条离谱**（回撤<−100% 或 年化 NaN）——")
            print("   ★★★ 说明闸还漏了一种情形，★ 这些数**不许用**：")
            print(离谱[["臂", "复合年化%", "最大回撤%", "缺价格的票", "现金低点"]]
                  .head(15).to_string(index=False))
        else:
            print("\n✅ 出表后复查：**没有回撤 <−100%、没有年化 NaN**")
    if len(df):
        print("\n★★★ 前 12 条（按卡玛排）：")
        c = [x for x in ["臂", "复合年化%", "最大回撖%", "最大回撤%", "卡玛", "在场率%",
                         "最长水下天数", "对SPY_alpha年%", "笔数"] if x in df.columns]
        print(df.sort_values("卡玛", ascending=False)[c].head(12).to_string(index=False))
    print("\n★★★★★ 自证待做（★ 本脚本不自己下结论）：拿已有的 21 条组合层 alpha 对一遍 —— "
          "★★★ 对不上就是重建错了。")


if __name__ == "__main__":
    main()
