#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 填说明书第 5 格 ——「这个条件在十二年里成立了多久 · 哪几年完全不成立」

★ 大白话:每条策略都有一个「什么时候才允许开仓」的大盘开关(regime)。
★★ 第 5 格问的是:**这个开关在这十年里开着的时间占多少、哪一年整年都没开过。**
★★★ 为什么这一格是必填:★ 如果一条策略只在 2020-2021 那两年成立,
   那它的十年平均成绩**没有意义** —— 用户买的是「它现在还成立吗」。

════════════════════════════════════════════════════════════════════
★★★ 为什么这个脚本不用等 engine 解冻
════════════════════════════════════════════════════════════════════
  ★ 它**只读**:只调 `matrices.build()` 算掩膜,不跑链、不动 engine 一个字节。
  ★★ 比跑链便宜两个数量级:**不要随机对照、不要 50 个种子、不要逐笔撮合**。
  ★★★ 而且同一个 (universe, regime) 规格**只算一次** ——
     45 条链里很多条共用同一套开关。

★ 口径(和老池重跑完全一致,否则第 5 格和第 7/8/11 格不可比):
    研发池 198 只(留出池 49 只一笔都不进) · large_mid · PERF 窗口
"""
from __future__ import annotations
import json, os, sys, hashlib, datetime
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
B1031 = os.path.join(ROOT, "probe", "bench1_rerun_1031")
B1102 = os.path.join(ROOT, "probe", "bench1_rerun_1102")
for p in (ROOT, B1031, B1102, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import data, matrices  # noqa: E402

CONFIG_DIR = os.path.join(ROOT, "engine", "configs")
HOLDOUT_JSON = os.path.join(B1031, "holdout_1031.json")
BENCH = os.path.join(B1102, "bench1_rerun_1102.json")
OUT = os.path.join(HERE, "第5格-按年-1102.json")


def say(*a):
    try:
        print(*a, flush=True)
    except Exception:
        pass


def 读配置(name: str) -> dict:
    import yaml
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        d = yaml.safe_load(fh)
    return d if isinstance(d, dict) else {}


def 规格指纹(cfg: dict) -> str:
    """★ 只有 universe + regime 这两块决定掩膜 —— ★★ 所以按这两块去重。
    ★★★ 必须剔掉 source / provenance / 注释类键,否则「只改了注释」也会被当成不同规格。"""
    def 洗(o):
        if isinstance(o, dict):
            return {k: 洗(v) for k, v in sorted(o.items())
                    if k not in ("source", "source_slots", "provenance", "note",
                                 "notes", "comment", "说明", "备注")}
        if isinstance(o, list):
            return [洗(x) for x in o]
        return o
    key = {"universe": 洗(cfg.get("universe") or {}),
           "regime": 洗(cfg.get("regime") or {})}
    s = json.dumps(key, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def 按年切(m, perf_mask) -> dict:
    """★ 返回逐年的两个数:
         ① regime 开着的交易日比例
         ② (universe & regime) 为真的票日比例
       ★★ 两个都要 —— ★★★ 开关开着但池子里没票,一样是「不成立」。"""
    # ★★★ perf_window 返回的是 DatetimeIndex,不是切片 —— ★ 这里要的是布尔掩膜
    idx = m.index[perf_mask]
    reg = np.asarray(m.regime)[perf_mask]
    uni = np.asarray(m.universe)[perf_mask]
    years = sorted({d.year for d in idx})
    out = {}
    for y in years:
        sel = np.array([d.year == y for d in idx])
        n = int(sel.sum())
        if not n:
            continue
        r = reg[sel]
        u = uni[sel]
        开着 = float(r.mean())
        # ★ 票日:当天开关开着 且 这只票在池里
        票日 = float((u & r[:, None]).mean()) if u.ndim == 2 else float((u & r).mean())
        out[str(y)] = {"交易日数": n,
                       "开关开着的交易日比例": round(开着, 6),
                       "开关开着的交易日数": int(r.sum()),
                       "掩膜为真的票日比例": round(票日, 6),
                       "★整年一天都没开过": bool(r.sum() == 0)}
    return out


def main() -> int:
    if not os.path.exists(BENCH):
        say(f"★ 拿不到老池重跑结果:{BENCH}"); return 2
    with open(BENCH, encoding="utf-8") as fh:
        bench = json.load(fh)
    链 = bench["逐链"]
    链 = list(链.values()) if isinstance(链, dict) else 链

    with open(HOLDOUT_JSON, encoding="utf-8") as fh:
        hd = json.load(fh)
    dev = list(hd["研发池名单"])
    hold = set(hd["留出池名单"])
    if set(dev) & hold:
        say("★★★ 研发池和留出池有交集,停"); return 3
    say(f"★ 研发池 {len(dev)} 只(留出池 {len(hold)} 只一笔都不进)")

    # ★★★ 按 (universe, regime) 规格去重 —— 同一套开关只算一次
    组: dict[str, dict] = {}
    for c in 链:
        name = c.get("配置")
        if not name:
            continue
        try:
            cfg = 读配置(name)
        except Exception as e:
            say(f"★ 读不到配置 {name}:{e}"); continue
        fp = 规格指纹(cfg)
        组.setdefault(fp, {"配置样本": name, "cfg": cfg, "链": []})["链"].append(c["链"])

    say(f"★★ 45 条链里只有 **{len(组)}** 套不同的 (universe, regime) 规格 "
        f"—— ★ 所以只算 {len(组)} 次,不是 45 次")

    结果 = {"这是什么": "说明书第 5 格:regime 开关按年的成立情况",
            "口径": {"池": f"研发池 {len(dev)} 只(留出池 {len(hold)} 只已排除)",
                    "窗口": f"{data.PERF_START} ~ {data.PERF_END}",
                    "★为什么可以不解冻": "只调 matrices.build() 算掩膜,不跑链,engine 一个字节没动"},
            "生成时间": f"{datetime.datetime.now():%Y-%m-%d %H:%M}",
            "逐规格": {}, "逐链指向规格": {}}

    for i, (fp, g) in enumerate(sorted(组.items()), 1):
        t0 = datetime.datetime.now()
        try:
            m = matrices.build(g["cfg"], dev)
            import pandas as _pd
            perf = ((m.index >= _pd.Timestamp(data.PERF_START)) &
                    (m.index <= _pd.Timestamp(data.PERF_END)))
            年 = 按年切(m, perf)
        except Exception as e:
            say(f"[{i}/{len(组)}] ★★★ 算不出来 {g['配置样本']}:{type(e).__name__}: {e}")
            结果["逐规格"][fp] = {"配置样本": g["配置样本"], "链": g["链"],
                                "★算不出来": f"{type(e).__name__}: {e}"}
            for k in g["链"]:
                结果["逐链指向规格"][k] = fp
            continue
        没开过 = [y for y, v in 年.items() if v["★整年一天都没开过"]]
        全开 = all(v["开关开着的交易日比例"] >= 0.999 for v in 年.values())
        结果["逐规格"][fp] = {
            "配置样本": g["配置样本"], "链数": len(g["链"]), "链": g["链"],
            "★这套开关是不是等于没有开关": 全开,
            "★整年一天都没开过的年份": 没开过,
            "全期开关开着的交易日比例": round(float(np.asarray(m.regime)[perf].mean()), 6),
            "全期交易日数": int(perf.sum()),
            "逐年": 年,
        }
        for k in g["链"]:
            结果["逐链指向规格"][k] = fp
        dt = (datetime.datetime.now() - t0).total_seconds()
        say(f"[{i}/{len(组)}] {g['配置样本'][:40]:42} "
            f"开着 {结果['逐规格'][fp]['全期开关开着的交易日比例']:.3f} "
            f"{'★等于没开关' if 全开 else ''} "
            f"{('★没开过的年:' + ','.join(没开过)) if 没开过 else ''} {dt:.1f}s")
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(结果, fh, ensure_ascii=False, indent=1)

    无开关 = sum(1 for v in 结果["逐规格"].values() if v.get("★这套开关是不是等于没有开关"))
    say("")
    say(f"★ 写出 {OUT}")
    say(f"★★★ {len(组)} 套规格里,**{无开关} 套等于没有开关**(全期都开着)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
