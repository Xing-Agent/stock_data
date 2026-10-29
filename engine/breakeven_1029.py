"""
breakeven_1029 —— 保本止损到底是净正还是净负?用我们自己的流水实测。

大白话(三秒):
  「赚到 1 倍风险(+1R)之后把止损挪到成本价」—— 这招看着稳,
  但它会把【先跌回成本价、后来才涨起来】的单子提前砍掉。
  砍掉的亏 vs 省下来的钱,谁大?这个脚本就量这一件事。

★★ 口径(硬性,不许变通)
  ① 触达 +1R ★ 一律按【收盘价】:Close ≥ entry_price + risk_per_share。
     ★ 严禁用盘中最高价 —— 日线策略没有日内撮合。
  ② 样本门槛:相关笔数 < 25 → 直接报「N 不足,不可采信」,★ 不给数。
  ③ 每条链都打印【前十笔占总盈利的比例】(集中度)。过半 → 结论里写明
     「这条链的收益数字不可用」,并把两侧读法都写出来。
  ④ 收益一律用【每笔收益率%】计量,★ 不用 R ——
     因为部分链 risk_per_share ≈ entry_price(其实没有止损),
     R 在那些链上无意义。

★★ 一条必须说出口的方法学意见(不是口径变通,是提醒读数的人)
  题目里的第(1)问「原实现下亏损离场的单子,事后又回到 +1R 的有多少」
  量的是【原有止损本身砍掉了多少好苗子】,★ 这不等于保本止损的代价:
  保本止损只作用在【已经摸到 +1R】的那批单子上,从没摸到 +1R 的单子
  它根本不参与。所以本脚本给三个数:
    · 代价A(照题目算):原实现亏损离场 → 事后回到 +1R 的笔数/占比
    · 代价B(保本止损真正的代价):摸到过 +1R、保本止损会把它在成本价砍掉、
      但原实现下它最终是【盈利】收场的那批单子,损失多少
    · 净效应:★ 以【全样本逐笔重放】为准 —— 对每笔摸到过 +1R 的单子,
      在 +1R 那天收盘之后把止损挪到成本价,首次收盘 ≤ 成本价就离场;
      其余单子原样不动。两种口径的【每笔平均收益率%】之差 = 净效应。
      这个数天然同时含了代价与收益,★ 不需要手工加减。

★ 实现细节
  · +1R 阈值 = entry_price + risk_per_share(流水里就有,不重算)
  · 扫描范围 = 这笔单子自己的持仓期 entry_date .. exit_date
  · 保本离场成交价:给两个边界 ——
      乐观界 = 成本价 entry_price(假定止损单在成本价成交)
      悲观界 = 触发那天的收盘价(跌穿时按收盘算,等于承认滑点)
    ★ 两个都报,净效应取【悲观界】作结论,避免自我美化。
  · 摩擦:沿用流水里的 friction_bps,双边计。
  · 代价A 的「事后窗口」:★ 与这笔单子自己的原持仓天数等长(对称),
    另给固定 20 / 60 个交易日做敏感性。

跑法:python3 -m engine.breakeven_1029
"""

from __future__ import annotations

import json
import os
import resource
import shutil
import subprocess
import time

import numpy as np
import pandas as pd

from . import cache, data

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROBE = os.path.join(ROOT, "probe", "breakeven_1029")
OUT_JSON = os.path.join(PROBE, "results_1029_保本止损.json")

# ★ 与上一轮时间止损测量用同一组流水目录,口径可比
LEDGER_DIRS = [
    os.path.join(HERE, "ledgers_1029_A0十二条_新拆股口径"),
    os.path.join(HERE, "ledgers_1029_技术派六条三版"),
    os.path.join(HERE, "ledgers_1029_批五修正"),
]

N_FLOOR = 25          # ★ 样本门槛
CONC_FLOOR = 0.50     # ★ 集中度过半 = 收益数字不可用


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _cache_fingerprint() -> dict:
    out = {}
    for label, path in (("ohlcv_panel.parquet", cache.PANEL_PARQUET),
                        ("panel_meta.parquet", cache.META_PARQUET)):
        st = os.stat(path)
        out[label] = {"bytes": st.st_size,
                      "构建时间(mtime, 本地)": time.strftime(
                          "%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))}
    return out


def _conc(led: pd.DataFrame) -> dict:
    """前十笔占总盈利的比例。分母 = 所有【盈利】笔子的毛盈亏之和。"""
    g = led["gross_pnl"].astype(float)
    pos = g[g > 0]
    if pos.empty:
        return {"前十笔占总盈利比例": None, "盈利笔数": 0,
                "★读法": "★ 没有盈利笔子,集中度无意义"}
    top10 = float(pos.nlargest(10).sum())
    share = top10 / float(pos.sum())
    if share > CONC_FLOOR:
        read = (f"★★ 集中度 {share:.1%} > 50% —— 【这条链的收益数字不可用】:"
                f"总收益几乎由前十笔决定,再多的样本也只是在重复这十笔的运气,"
                f"任何「净正/净负 X%」在这里都是噪音。"
                f"(反过来读:若集中度在一两成以内,说明收益是由"
                f"几百笔共同堆出来的,这时的净效应才是可以当作策略属性来用的数。)")
    elif share <= 0.20:
        read = (f"★ 集中度 {share:.1%} ≤ 20% —— 收益由大量笔子共同堆出,"
                f"净效应可以当作这条链的策略属性来用。"
                f"(反过来读:若过半,就只是在重复前十笔的运气,数字不可用。)")
    else:
        read = (f"★ 集中度 {share:.1%} —— 介于两侧之间:不至于「只是十笔运气」,"
                f"但也还没到「几百笔共同堆出」的程度,净效应当作参考、"
                f"不要当作精确值。"
                f"(两侧读法:过半 = 数字不可用;一两成以内 = 可当策略属性。)")
    return {"前十笔占总盈利比例": round(share, 4),
            "盈利笔数": int(pos.size),
            "★读法": read}


def one_ledger(path: str, close: pd.DataFrame, row_of: dict) -> dict:
    led = pd.read_csv(path)
    name = os.path.basename(path)[:-4]
    n = len(led)
    if n == 0:
        return {"链": name, "总笔数": 0, "★结论": "★ 拿不到:流水是空的"}

    ca = close.to_numpy(float)
    cols = {s: i for i, s in enumerate(close.columns)}
    nrow = ca.shape[0]

    rd = (led["risk_per_share"].astype(float)
          / led["entry_price"].astype(float)).replace([np.inf, -np.inf], np.nan)
    no_stop = float((rd >= 0.999).mean())

    # 逐笔重放
    act_ret = []          # 原实现每笔净收益率
    be_ret_opt = []       # 保本口径·乐观界(成本价成交)
    be_ret_pes = []       # 保本口径·悲观界(触发日收盘成交)
    hit1r = []            # 是否收盘触达过 +1R
    be_fired = []         # 保本止损是否真的被触发
    missing = 0

    # 代价A:原实现亏损离场的单子,事后回到 +1R
    costA_den = 0
    costA_hit = {"同持仓期等长": 0, "固定20日": 0, "固定60日": 0}

    # 代价B / 收益:分桶明细
    detail = []

    for _, r in led.iterrows():
        s = r["symbol"]
        i0 = row_of.get(pd.Timestamp(r["entry_date"]))
        i1 = row_of.get(pd.Timestamp(r["exit_date"]))
        if s not in cols or i0 is None or i1 is None:
            missing += 1
            continue
        j = cols[s]
        ep = float(r["entry_price"])
        thr = ep + float(r["risk_per_share"])
        fb = float(r["friction_bps"]) / 10000.0
        a_gross = float(r["gross_return"])
        a_net = a_gross - 2 * fb          # 双边摩擦,按收益率口径
        act_ret.append(a_net)

        seg = ca[i0:i1 + 1, j]
        ok = np.flatnonzero(np.isfinite(seg) & (seg >= thr))
        hit = bool(ok.size)
        hit1r.append(hit)

        # ---- 代价A ----
        if a_gross <= 0:
            costA_den += 1
            hold = max(1, int(i1 - i0))
            for lab, w in (("同持仓期等长", hold), ("固定20日", 20),
                           ("固定60日", 60)):
                k0, k1 = i1 + 1, min(nrow, i1 + 1 + w)
                if k1 > k0:
                    fw = ca[k0:k1, j]
                    if np.any(np.isfinite(fw) & (fw >= thr)):
                        costA_hit[lab] += 1

        # ---- 保本止损重放 ----
        if not hit:
            be_ret_opt.append(a_net)
            be_ret_pes.append(a_net)
            be_fired.append(False)
            continue
        d1r = int(ok[0])
        after = seg[d1r + 1:]
        trg = np.flatnonzero(np.isfinite(after) & (after <= ep))
        if trg.size == 0:
            be_ret_opt.append(a_net)
            be_ret_pes.append(a_net)
            be_fired.append(False)
            continue
        k = d1r + 1 + int(trg[0])
        be_fired.append(True)
        o_net = 0.0 - 2 * fb                      # 成本价成交
        p_net = (float(seg[k]) / ep - 1.0) - 2 * fb   # 触发日收盘成交
        be_ret_opt.append(o_net)
        be_ret_pes.append(p_net)
        detail.append({"actual": a_net, "opt": o_net, "pes": p_net,
                       "actual_win": a_gross > 0})

    m = len(act_ret)
    if m == 0:
        return {"链": name, "总笔数": n,
                "★结论": "★ 拿不到:流水里没有一笔能对上价格面板"}

    a = np.asarray(act_ret)
    bo = np.asarray(be_ret_opt)
    bp = np.asarray(be_ret_pes)
    hitm = np.asarray(hit1r)
    firedm = np.asarray(be_fired)

    n_hit = int(hitm.sum())
    n_fired = int(firedm.sum())
    # 保本止损触发的那批里,原实现本来是盈利的(= 代价B)/ 亏损的(= 收益)
    d_win = [d for d in detail if d["actual_win"]]
    d_los = [d for d in detail if not d["actual_win"]]

    def _mean(xs, key):
        return float(np.mean([x[key] for x in xs])) if xs else None

    out: dict = {
        "链": name,
        "总笔数": n,
        "参与测算的笔数": m,
        "对不上价格的笔数": missing,
        "★★「其实没有止损」的笔数占比(risk÷entry ≥0.999)": round(no_stop, 4),
        "风险距离中位(risk÷entry)": round(float(rd.median()), 4),
        "集中度": _conc(led),
        "原实现·每笔平均收益率%": round(float(a.mean()) * 100, 4),
        "★收盘触达过+1R的笔数": n_hit,
        "★保本止损会被触发的笔数": n_fired,
    }

    # ---- 第(1)问 代价A ----
    cA: dict = {"分母(原实现亏损/止损离场的笔数)": costA_den}
    if costA_den < N_FLOOR:
        cA["★结论"] = f"★★ N 不足({costA_den} < {N_FLOOR}),不可采信,不给数"
    else:
        for lab, v in costA_hit.items():
            cA[f"事后回到+1R的笔数_{lab}"] = v
            cA[f"占比_{lab}"] = round(v / costA_den, 4)
        cA["★读法"] = ("★ 这个数量的是【原有止损本身砍掉了多少好苗子】,"
                       "★ 不是保本止损的代价 —— 这批单子大多从没摸到 +1R,"
                       "保本止损对它们不起作用。保本止损真正的代价见「代价B」。")
    out["①保本止损的代价A(照题目口径)"] = cA

    # ---- 第(2)问 收益 + 代价B ----
    gain: dict = {"分母(摸到+1R、保本止损会触发、且原实现亏损收场)": len(d_los)}
    if len(d_los) < N_FLOOR:
        gain["★结论"] = f"★★ N 不足({len(d_los)} < {N_FLOOR}),不可采信,不给数"
    else:
        gain["原实现·这批的平均收益率%"] = round(_mean(d_los, "actual") * 100, 4)
        gain["保本口径·乐观界(成本价成交)平均收益率%"] = round(
            _mean(d_los, "opt") * 100, 4)
        gain["保本口径·悲观界(触发日收盘成交)平均收益率%"] = round(
            _mean(d_los, "pes") * 100, 4)
        gain["★省下来(乐观界)每笔百分点"] = round(
            (_mean(d_los, "opt") - _mean(d_los, "actual")) * 100, 4)
        gain["★省下来(悲观界)每笔百分点"] = round(
            (_mean(d_los, "pes") - _mean(d_los, "actual")) * 100, 4)
    out["②保本止损的收益"] = gain

    costB: dict = {"分母(摸到+1R、保本止损会触发、但原实现盈利收场)": len(d_win)}
    if len(d_win) < N_FLOOR:
        costB["★结论"] = f"★★ N 不足({len(d_win)} < {N_FLOOR}),不可采信,不给数"
    else:
        costB["原实现·这批的平均收益率%"] = round(_mean(d_win, "actual") * 100, 4)
        costB["保本口径·乐观界平均收益率%"] = round(_mean(d_win, "opt") * 100, 4)
        costB["保本口径·悲观界平均收益率%"] = round(_mean(d_win, "pes") * 100, 4)
        costB["★砍掉的(乐观界)每笔百分点"] = round(
            (_mean(d_win, "opt") - _mean(d_win, "actual")) * 100, 4)
        costB["★砍掉的(悲观界)每笔百分点"] = round(
            (_mean(d_win, "pes") - _mean(d_win, "actual")) * 100, 4)
    costB["★读法"] = ("★ 这批就是「先回踩到成本价、后来才涨上去」的单子 —— "
                      "保本止损把它们提前砍掉了。这是保本止损真正的代价。")
    out["①′保本止损的代价B(真正的代价)"] = costB

    # ---- 第(3)问 净效应:全样本逐笔重放 ----
    net: dict = {}
    if n_fired < N_FLOOR:
        net["★结论"] = (f"★★ N 不足:保本止损只会触发 {n_fired} 笔"
                        f"(< {N_FLOOR}),净效应不可采信,不给数")
    else:
        net["样本(全样本逐笔重放的笔数)"] = m
        net["保本止损触发笔数"] = n_fired
        net["原实现·每笔平均收益率%"] = round(float(a.mean()) * 100, 4)
        net["保本口径·乐观界 每笔平均收益率%"] = round(float(bo.mean()) * 100, 4)
        net["保本口径·悲观界 每笔平均收益率%"] = round(float(bp.mean()) * 100, 4)
        net["★净效应(乐观界)每笔百分点"] = round(
            float(bo.mean() - a.mean()) * 100, 4)
        net["★净效应(悲观界·作结论用)每笔百分点"] = round(
            float(bp.mean() - a.mean()) * 100, 4)
        # 手工加减版(题目口径):收益 − 代价B,摊到全样本
        if len(d_los) >= N_FLOOR and len(d_win) >= N_FLOOR:
            saved = sum(d["pes"] - d["actual"] for d in d_los)
            cut = sum(d["actual"] - d["pes"] for d in d_win)
            net["对账·省下来合计(悲观界)百分点"] = round(saved * 100, 2)
            net["对账·砍掉合计(悲观界)百分点"] = round(cut * 100, 2)
            net["对账·(省−砍)÷全样本笔数 百分点"] = round(
                (saved - cut) / m * 100, 4)
        sgn = float(bp.mean() - a.mean())
        net["★净正还是净负"] = ("净正" if sgn > 0 else
                                 ("净负" if sgn < 0 else "持平"))
    out["③净效应"] = net

    if no_stop > 0.5:
        out["★★口径警报"] = (
            f"★★ 这条链 {no_stop:.0%} 的笔子 risk_per_share ≈ entry_price "
            f"—— 止损价挂在 0,其实没有止损。于是「+1R」= 股价翻倍,"
            f"触达笔数必然接近 0 ★ 这条链的保本止损结论无效,先修口径。")
    return out


def main() -> int:
    t0 = time.time()
    os.makedirs(PROBE, exist_ok=True)
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()

    syms = cache.symbols()
    close = cache.field("close", syms)
    row_of = {t: i for i, t in enumerate(close.index)}
    print(f"池子 {len(syms)} 只;价格面板 {close.shape}")

    rows = []
    for d in LEDGER_DIRS:
        if not os.path.isdir(d):
            print(f"★ 目录不存在,跳过:{d}")
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".csv"):
                continue
            src = os.path.join(d, f)
            rec = one_ledger(src, close, row_of)
            rec["流水目录"] = os.path.basename(d)
            rows.append(rec)
            # ★ 流水落盘到 probe 下,把这次测量的输入钉死
            dst = os.path.join(PROBE, "ledgers", os.path.basename(d))
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(src, os.path.join(dst, f))
            net = rec.get("③净效应", {})
            print(f"  {rec['链'][:44]:46s} n={rec['总笔数']:5d} "
                  f"触发={rec.get('★保本止损会被触发的笔数', 0):4d} "
                  f"净={net.get('★净效应(悲观界·作结论用)每笔百分点', '—')}")

    focus = [r for r in rows
             if any(k in r["链"] for k in ("技-8", "技-13", "技-10"))]
    out = {
        "git_commit": head,
        "缓存身份": _cache_fingerprint(),
        "统计窗口": [data.PERF_START, data.PERF_END],
        "★口径": {
            "触达+1R": "★ 按【收盘价】Close ≥ entry_price + risk_per_share;"
                        "★ 严禁用盘中最高价",
            "保本触发": "+1R 那天之后,首次收盘 ≤ entry_price",
            "成交价": "乐观界 = 成本价;悲观界 = 触发日收盘价(★ 结论取悲观界)",
            "计量": "★ 每笔收益率%,不用 R(部分链没有真实止损距离)",
            "样本门槛": f"相关笔数 < {N_FLOOR} → 报「N 不足,不可采信」,不给数",
            "集中度": "前十笔毛盈利 ÷ 全部盈利笔毛盈利之和;"
                      f"> {CONC_FLOOR:.0%} → 该链收益数字不可用",
            "并行": "★ 串行跑,单进程(机器 2 核 / 7GB)",
        },
        "逐链": rows,
        "★重点三条(技-8 / 技-13 / 技-10)": focus,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT_JSON}(共 {len(rows)} 条链;"
          f"{time.time()-t0:.0f} 秒;峰值 RSS {_rss_mb():.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
