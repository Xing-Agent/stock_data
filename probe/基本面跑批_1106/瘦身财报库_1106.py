# -*- coding: utf-8 -*-
"""
★★★ 财报库「瘦身副本」+ 进程内读法 —— ★ 为了不被 OOM 杀掉。engine 零改动。

★★ 为什么要它（★ 查出来的，不是猜的）:
  `接新财报库_1106._读` 是 `lru_cache(maxsize=8192)`，缓存的是**整份解析后的 JSON**
  （每条记录 ~25 个字段：accession / source_url / taxonomy …）。
  ★ 一只票解析后约十几 MB，研发池 2,224 只 → ★★★ 光这一个缓存就要几十 GB，
    而环境只有 7GB —— ★ 这很可能就是「跑到第 8 条臂左右被 OOM 杀掉」的原因之一。
★★ 做法:一次性把研发池每只票的财报**只留引擎读的 6 个字段**
  (filing_date / accepted_at / filed_at / period_start / period_end / value)
  存成每票一个 pickle;运行时**不缓存整份**,每次按需从盘上读。
  ★★★ 引擎读到的内容**一字不差**(同样的记录、同样的值、同样的顺序)——
    只是丢掉了引擎从来不读的字段。下面 `自检()` 逐条对过。
★ 没命中(瘦身库里没有这只)→ 原样转回原函数,不悄悄返回空。
"""
from __future__ import annotations
import gzip, json, os, pickle, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXT = os.path.join(ROOT, "fundamentals_ext")
SLIM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_slim_fund")
KEEP = ("filing_date", "accepted_at", "filed_at", "period_start", "period_end", "value")
_装过 = False


def _slim_one(sym: str) -> dict | None:
    p = os.path.join(EXT, sym, "fundamentals.json.gz")
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        d = json.load(fh)
    fv = d.get("financial_versions")
    if not isinstance(fv, dict):
        return None
    return {m: [tuple(r.get(k) for k in KEEP) for r in (rs or [])]
            for m, rs in fv.items()}


def 建(symbols: list[str]) -> dict:
    os.makedirs(SLIM, exist_ok=True)
    t0, n, miss = time.time(), 0, []
    for s in symbols:
        out = os.path.join(SLIM, f"{s}.pkl")
        if os.path.exists(out):
            n += 1; continue
        r = _slim_one(s)
        if r is None:
            miss.append(s); continue
        with open(out, "wb") as fh:
            pickle.dump(r, fh, protocol=pickle.HIGHEST_PROTOCOL)
        n += 1
    return {"建好": n, "★新库里没有的": len(miss), "没有的前10": miss[:10],
            "耗时秒": round(time.time() - t0, 1)}


class _Lazy(dict):
    """★ 只在 .get(metric) 时把那一个科目还原成记录表(dict),不整份展开。"""
    def __init__(self, raw: dict):
        super().__init__()
        self._raw = raw

    def get(self, k, default=None):
        rs = self._raw.get(k)
        if rs is None:
            return default
        return [dict(zip(KEEP, t)) for t in rs]

    def __contains__(self, k):
        return k in self._raw

    def keys(self):
        return self._raw.keys()


def install() -> dict:
    global _装过
    from engine import data as D, fundamentals as F
    if _装过:
        return {"★已装过": True}
    旧 = D.load_fundamentals

    def 新(symbol: str):
        p = os.path.join(SLIM, f"{symbol}.pkl")
        if os.path.exists(p):
            with open(p, "rb") as fh:
                return _Lazy(pickle.load(fh))
        return 旧(symbol)          # ★★★ 没命中 → 原样转回原函数

    D.load_fundamentals = 新
    for fn in (getattr(F, "quarterly", None), getattr(F, "ttm", None),
               getattr(F, "quarter_frame", None), getattr(F, "shares_quarterly", None),
               getattr(F, "panel", None)):
        if fn is not None and hasattr(fn, "cache_clear"):
            fn.cache_clear()
    _装过 = True
    return {"★瘦身库装上了": True, "只数": len(os.listdir(SLIM)) if os.path.isdir(SLIM) else 0}


def 自检(syms: list[str]) -> dict:
    """★★★ 逐条对:瘦身读法 vs 原读法,引擎读的 6 个字段必须一字不差。"""
    bad = []
    for s in syms:
        r0 = json.load(gzip.open(os.path.join(EXT, s, "fundamentals.json.gz"), "rt",
                                 encoding="utf-8")).get("financial_versions") or {}
        r1 = _Lazy(pickle.load(open(os.path.join(SLIM, f"{s}.pkl"), "rb")))
        for m, rs in r0.items():
            a = [{k: r.get(k) for k in KEEP} for r in rs]
            if a != (r1.get(m) or []):
                bad.append((s, m))
    return {"对了几只": len(syms), "不一致": bad[:10], "不一致数": len(bad)}


if __name__ == "__main__":
    sys.path.insert(0, ROOT); os.chdir(ROOT)
    h = json.load(open("probe/新策略_1106/holdout_newpool_1106.json", encoding="utf-8"))
    dev = h["研发池名单"]
    print(json.dumps(建(dev), ensure_ascii=False))
    import hashlib
    samp = sorted(dev, key=lambda s: hashlib.sha256(s.encode()).hexdigest())[:20]
    print(json.dumps(自检([s for s in samp if os.path.exists(os.path.join(SLIM, s + ".pkl"))]),
                     ensure_ascii=False))
