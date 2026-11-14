#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微仓全接诊断（2026-11-14 · Lin 1112 拍板《172》第 4 条 / 要干啥第 1 条）

大白话：正常版一次最多拿 10 只，信号多的时候只能挑一部分。
       这里另跑一版「每个信号都接、每笔只下一丁点」，看两件事：
       我们挑中的那批，比全部信号好多少；被丢掉的那批，成绩怎样。

每条策略比四个数（拍板原文）：
  1 信号成交率      = 正常版成交笔数 / 微仓版成交笔数
  2 排序提升度      = 成交那批的每笔均收益 − 全部信号的每笔均收益
  3 被丢信号的成绩  = 微仓版里、正常版没接的那批
  4 起始日挪 0~4 天 = 正常版五次的复合年化的标准差

微仓版只改三处仓位参数：单笔风险 0.01%、单只上限 0.1%、max_positions 1000。
engine/ 一个字节不改：配置是读进内存后再覆盖的，文件不动。
只用研发池；每条策略一个子进程，跑完立刻落盘，可续跑。
"""
import copy
import glob
import io
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
LED = os.path.join(HERE, "ledgers")
DIRS = ["probe/基本面跑批_1106/configs", "probe/fundamental_buildout_1030/configs_1030",
        "probe/新策略_1106/configs", "engine/configs"]
SKIP = ("_TEMPLATE", "buy_and_hold")
CAP0 = 1_000_000.0


def 清单():
    out = []
    for d in DIRS:
        for f in sorted(glob.glob(os.path.join(ROOT, d, "*.yaml"))):
            b = os.path.basename(f)[:-5]
            if b.startswith(SKIP):
                continue
            out.append({"名": b, "路": os.path.relpath(f, ROOT)})
    return out


def 出文件(名):
    return os.path.join(OUT, 名.replace("/", "_").replace(" ", "_") + ".json")


def 每笔(led):
    r = (led["net_pnl"] / led["notional_in"]).astype(float)
    return r


def 摘要(led):
    if not len(led):
        return {"笔数": 0}
    r = 每笔(led)
    赚 = float(r[r > 0].sum())
    亏 = float(-r[r < 0].sum())
    return {"笔数": int(len(led)), "每笔均收益pct": round(float(r.mean() * 100), 4),
            "每笔中位pct": round(float(r.median() * 100), 4),
            "胜率pct": round(float((r > 0).mean() * 100), 1),
            "利润因子_等权每笔": (round(赚 / 亏, 3) if 亏 > 0 else None)}


def 年化(led, start, end):
    import pandas as pd
    yrs = (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25
    tot = float(led["net_pnl"].sum()) if len(led) else 0.0
    v = (CAP0 + tot) / CAP0
    if v <= 0 or yrs <= 0:
        return None
    return v ** (1 / yrs) - 1


def 跑一条(item):
    sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
    import yaml
    import pandas as pd
    import numpy as np
    import 跑基本面_1106 as B
    RC, 层 = B.装层()
    from engine import chain, matrices, data
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw0 = yaml.safe_load(io.open(os.path.join(ROOT, item["路"]), encoding="utf-8"))
    t0 = time.time()
    cfg0 = chain.ChainConfig.from_dict(copy.deepcopy(raw0))
    m = matrices.build(cfg0.raw, dev)
    RC.apply_scope(m, B.SCOPE)
    建秒 = round(time.time() - t0, 1)
    start, end = data.PERF_START, data.PERF_END

    def 跑(raw, s=start):
        cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
        led = chain.run_chain(cfg, dev, s, end, m=m).ledger
        if len(led):
            漏 = set(led["symbol"].astype(str)) & hs
            if 漏:
                raise RuntimeError(f"留出池漏进来 {len(漏)} 只")
        return led

    正 = 跑(raw0)
    微raw = copy.deepcopy(raw0)
    sz = 微raw.setdefault("sizing", {}) or {}
    微raw["sizing"] = sz
    p = sz.setdefault("params", {}) or {}
    sz["params"] = p
    原仓位 = {k: p.get(k) for k in ("risk_per_trade", "max_weight", "max_positions")}
    if "risk_per_trade" in p or sz.get("type") in (None, "risk_fraction"):
        p["risk_per_trade"] = 0.0001
    p["max_weight"] = 0.001
    p["max_positions"] = 1000
    微 = 跑(微raw)
    os.makedirs(LED, exist_ok=True)
    正.to_csv(os.path.join(LED, f"正常__{item['名']}.csv"), index=False)
    微.to_csv(os.path.join(LED, f"微仓__{item['名']}.csv"), index=False)

    rec = {"名": item["名"], "配置": item["路"], "窗口": f"{start} → {end}",
           "池": f"研发池 {len(dev)} 只（留出池 {len(hs)} 只已排除）",
           "原仓位参数": 原仓位, "仓位类型": sz.get("type"),
           "建矩阵秒": 建秒, "正常版": 摘要(正), "微仓版_全部信号": 摘要(微)}
    if len(微) and len(正):
        k = lambda d: set(zip(d["symbol"].astype(str), d["entry_date"].astype(str)))
        正键, 微键 = k(正), k(微)
        在 = pd.Series([x in 正键 for x in zip(微["symbol"].astype(str), 微["entry_date"].astype(str))],
                      index=微.index)
        接, 丢 = 微[在], 微[~在]
        rec["1_信号成交率pct"] = round(len(正) / len(微) * 100, 2)
        rec["对得上的笔数"] = int(在.sum())
        rec["正常版里微仓版没有的笔数"] = int(len(正键 - 微键))
        rec["成交那批_按微仓版口径"] = 摘要(接)
        rec["3_被丢信号"] = 摘要(丢)
        if len(接):
            rec["2_排序提升度pct"] = round(float((每笔(接).mean() - 每笔(微).mean()) * 100), 4)
        # 微仓版是不是真的「全接」了：1000 个位子有没有被占满过
        rec["微仓版同时持仓上限占用"] = "见流水" if "entry_date" not in 微 else int(
            pd.concat([pd.Series(1, index=pd.to_datetime(微["entry_date"])),
                       pd.Series(-1, index=pd.to_datetime(微["exit_date"]))]).sort_index().cumsum().max()
        ) if "exit_date" in 微 else None
    # 4 起始日挪 0~4 个交易日
    idx = m.index
    days = [str(d.date()) for d in idx[idx >= pd.Timestamp(start)][:5]]
    挪 = []
    for i, s in enumerate(days):
        led = 正 if i == 0 and s == str(pd.Timestamp(start).date()) else 跑(raw0, s)
        a = 年化(led, s, end)
        挪.append({"起始日": s, "笔数": int(len(led)),
                   "复合年化pct": None if a is None else round(a * 100, 3)})
    rec["4_起始日挪动"] = 挪
    v = [x["复合年化pct"] for x in 挪 if x["复合年化pct"] is not None]
    rec["4_年化标准差pct"] = round(float(np.std(v, ddof=1)), 3) if len(v) >= 2 else None
    rec["总秒"] = round(time.time() - t0, 1)
    return rec


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    if "--one" in argv:
        名 = argv[argv.index("--one") + 1]
        item = next(x for x in 清单() if x["名"] == 名)
        try:
            rec = 跑一条(item)
        except Exception as e:
            rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2500:]}
        io.open(出文件(名), "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    只 = argv[argv.index("--only") + 1] if "--only" in argv else None
    L = 清单()
    print(f"共 {len(L)} 条", flush=True)
    for it in L:
        if 只 and not it["名"].startswith(只):
            continue
        if os.path.exists(出文件(it["名"])):
            continue
        t = time.time()
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", it["名"]], cwd=ROOT)
        if not os.path.exists(出文件(it["名"])):
            io.open(出文件(it["名"]), "w", encoding="utf-8").write(json.dumps(
                {"名": it["名"], "跑失败": f"子进程退出码 {r.returncode}（多半是内存被杀）"}, ensure_ascii=False))
        print(f"   {it['名']}  {time.time() - t:.0f}s", flush=True)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
