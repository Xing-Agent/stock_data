# -*- coding: utf-8 -*-
"""
★★★ 技-7 / 技-8 / 技-9 跑批（B 路 1106）—— 新池研发池,相邻三点,大盘替身修正口径 C

★ 每条主扫一个原著没给的数(规矩②),报三点是否同向;技-7 另跑一版「贴着交报表日」,技-8 另跑原著不加时间止损版。
★ 可续跑:每条臂流水落盘(arms_1106/,不入库);engine 零改动;只用研发池;不跑赢随机;失败大声报。
"""
from __future__ import annotations
import copy, gc, io, json, os, sys, time, traceback
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "probe", "挂件_1106"))
import 台_公共_1106 as T                                            # noqa: E402

ARMS = os.path.join(HERE, "arms_1106")
OUT = os.path.join(HERE, "技789结果_1106.json")
C = os.path.join(HERE, "configs")


def 改(raw, path, val):
    d = copy.deepcopy(raw); cur = d; ps = path.split(".")
    for k in ps[:-1]:
        cur = cur[int(k)] if k.isdigit() else cur[k]
    cur[ps[-1]] = val
    return d


def 臂表():
    out = []
    r7 = T.读配置(os.path.join(C, "技-7_库拉麦吉EP.yaml"))
    for g in (0.08, 0.10, 0.15):
        out.append(("技-7", f"跳空≥{int(g*100)}%", 改(r7, "entry.rules.0.params.gap_min", g)))
    out.append(("技-7", "跳空≥10%·贴着交报表日(2日内)", 改(r7, "entry.rules.0.params.near_filing_days", 2)))
    r8 = T.读配置(os.path.join(C, "技-8_高紧旗形HTF.yaml"))
    for pb in (0.20, 0.25):
        for n in (3, 5):
            r = 改(r8, "entry.rules.0.params.max_pullback", pb)
            r = 改(r, "trailing_stop.stages.0.when.days_held_gte", n)
            r = 改(r, "trailing_stop.stages.0.when.days_held_lte", n)
            out.append(("技-8", f"回调≤{int(pb*100)}%·第{n}天不启动就走", r))
    r = 改(r8, "entry.rules.0.params.max_pullback", 0.20)
    r["trailing_stop"] = {"type": "none", "source": "对照:原著不加时间止损"}
    out.append(("技-8", "回调≤20%·不加时间止损(对照)", r))
    r9 = T.读配置(os.path.join(C, "技-9_次新股首发底.yaml"))
    for n in (15, 20, 25):
        r = 改(r9, "entry.rules.0.params.base_bars", n)
        r = 改(r, "initial_stop.params.structure_lookback", n)
        out.append(("技-9", f"整理段{n}日", r))
    return out


def 单臂(led: pd.DataFrame) -> dict:
    if len(led) == 0:
        return {"笔数": 0, "★": "一笔都没有"}
    d = T._键(led)
    s = T.替身收益(d)
    x = (d["ret"] - s).dropna()
    日 = d.loc[x.index, "entry_date"].dt.strftime("%Y-%m-%d")
    r = T.聚类t(x, 日)
    bb = T.块重抽样(x, 日)
    return {"笔数": int(len(d)), "★同票同日重复被丢": d.attrs["丢重复"],
            "每笔净收益pct": round(float(d["ret"].mean()) * 100, 4),
            "利润因子": T._pf(d), "胜率": round(float((d["net_pnl"] > 0).mean()), 4),
            "★比同期大盘pct": round(r["均值"] * 100, 4),
            "t": round(r["t"], 2) if np.isfinite(r["t"]) else None,
            "月块95%区间pct": [round(v * 100, 4) for v in bb["95%区间"]] if bb.get("95%区间") else None,
            "★★★判定": T.判(r["t"], bb.get("区间不含0", False)) if len(d) >= 30 else "★笔数<30,不判",
            "平均持有天": round(float(d["holding_days"].mean()), 2),
            "离场原因": d["reason"].value_counts().to_dict(),
            "流水哈希": T.流水哈希(led)}


def main() -> int:
    t0 = time.time()
    env = T.装覆盖层()
    import 技789覆盖层_1106 as O
    O.install()
    os.makedirs(ARMS, exist_ok=True)
    报 = {"★口径": {k: v for k, v in env.items() if not k.startswith("_")}}
    报["★口径"].update({"判据": "大盘替身修正口径 C(不扔当天单、时点对齐);进场日聚类 t + 月块重抽样",
                       "engine改动": "零(pat6 + 技789 两层覆盖)", "赢随机": "不跑(已作废)"})
    失败 = []
    for 卡, 名, raw in 臂表():
        label = f"{卡}|{名}"
        p = T.臂文件(ARMS, label)
        try:
            if os.path.exists(p):
                led = pd.read_csv(p); print("  ⟳", label, flush=True)
            else:
                tb = time.time()
                m, diag = T.建矩阵(raw)
                led, info = T.跑(raw, m)
                del m; gc.collect()
                led.to_csv(p, index=False)
                print(f"  ✓ {label} {len(led)} 笔 {time.time()-tb:.0f}s", flush=True)
            报.setdefault(卡, {})[名] = 单臂(led)
        except Exception as e:
            失败.append({"臂": label, "原因": f"{type(e).__name__}: {e}"[:300]})
            报.setdefault(卡, {})[名] = {"★跑失败": traceback.format_exc(limit=3)[-600:]}
            print("  ✗✗✗", label, e, flush=True)
    # ★ 规矩⑪:流水哈希相同 = 同一个版本
    for 卡, v in 报.items():
        if 卡.startswith("★"):
            continue
        hs = {}
        for 名, r in v.items():
            if isinstance(r, dict) and r.get("流水哈希"):
                hs.setdefault(r["流水哈希"], []).append(名)
        dup = [x for x in hs.values() if len(x) > 1]
        if dup:
            v["★名字不同·流水相同(只算一个版本)"] = dup
    报["★★★失败"] = 失败
    报["耗时秒"] = round(time.time() - t0, 1)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写到 {OUT};失败 {len(失败)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
