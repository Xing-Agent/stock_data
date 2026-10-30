"""把 300 只有日线的票映射到 1030 新池口径(大盘+中盘 = 成交额排名 1–2000)。

大白话:我们手上只有 300 只票的日线。新口径说「只做排名 1–2000 名」。
        所以这一步做的是:这 300 只里,哪几只在那 2000 名之内。
        不是「从 6000 只里挑 2000 只」—— 那 2000 只里绝大多数我们没有日线。

★ 纪律 4:池子用当年年初代码(ANTM),我们的 manifest 用最终代码(ELV)。
  → 先把 manifest 的 symbol 解析成 company_id,再用 company_id + year 对。
"""
from __future__ import annotations
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

POOL_CSV = os.path.join(ROOT, "probe", "survivorship_1029", "pool_FULL_ALL.csv")

#: 口径戳 —— 报告里必须原样引用这一行
SCOPE_FILTER_LINE = "pool[pool['rank'] <= 2000]   # == pool['tier'].isin(['大','中'])"
RANK_MAX = 2000


def load_pool() -> pd.DataFrame:
    p = pd.read_csv(POOL_CSV, dtype={"symbol": str, "renamed_to": str,
                                     "old_symbol": str, "tier": str})
    assert len(p) == 74268, f"池子行数对不上:{len(p)} != 74268"
    # 验证 tier 与 rank 两种写法等价(★ 同一样东西两种写法)
    a = set(map(tuple, p.loc[p["rank"] <= RANK_MAX, ["year", "company_id"]].values))
    b = set(map(tuple, p.loc[p["tier"].isin(["大", "中"]), ["year", "company_id"]].values))
    assert a == b, "tier 与 rank<=2000 不等价 —— 停下来查"
    return p


def resolve_company_ids(pool: pd.DataFrame, symbols: list[str]) -> dict[str, set[int]]:
    """symbol → company_id 集合。三列都查:当年代码 / 改名后 / 改名前。"""
    idx: dict[str, set[int]] = {}
    for col in ("symbol", "renamed_to", "old_symbol"):
        sub = pool[["company_id", col]].dropna()
        for cid, s in sub.itertuples(index=False):
            s = str(s).strip()
            if s and s.lower() != "nan":
                idx.setdefault(s, set()).add(int(cid))
    return {s: idx.get(s, set()) for s in symbols}


def membership(pool: pd.DataFrame, cids: dict[str, set[int]]) -> pd.DataFrame:
    """逐票 × 逐年:当年是否 rank<=2000,以及当年的 rank / tier。"""
    inscope = pool[pool["rank"] <= RANK_MAX]
    key = {}
    for y, cid, rk, tr in inscope[["year", "company_id", "rank", "tier"]].itertuples(index=False):
        key[(int(y), int(cid))] = (int(rk), tr)
    any_year = {}
    for y, cid in pool[["year", "company_id"]].itertuples(index=False):
        any_year.setdefault(int(cid), set()).add(int(y))
    rows = []
    for s, cs in cids.items():
        for y in range(2015, 2027):
            hit = [key[(y, c)] for c in cs if (y, c) in key]
            present = any(y in any_year.get(c, ()) for c in cs)
            rows.append({"symbol": s, "year": y, "in_pool_any": present,
                         "in_scope": bool(hit),
                         "rank": min(h[0] for h in hit) if hit else None,
                         "tier": (min(hit)[1] if hit else None)})
    return pd.DataFrame(rows)


#: 分段口径 —— 「这一段里过半数年份排名 1–2000」才算这一段的样本
PERIODS = {"2018-2022": list(range(2018, 2023)),
           "2023-2025": list(range(2023, 2026)),
           "2018-2020": list(range(2018, 2021)),
           "2021-2022": list(range(2021, 2023)),
           "全期2018-2025": list(range(2018, 2026))}


def scope_sets(mem: pd.DataFrame) -> dict[str, list[str]]:
    out = {}
    for name, years in PERIODS.items():
        sub = mem[mem["year"].isin(years)]
        g = sub.groupby("symbol")["in_scope"].mean()
        out[name] = sorted(g[g > 0.5].index)
    return out


if __name__ == "__main__":
    import engine.data as D
    man = D.load_manifest()
    syms = sorted(man)
    print(f"有日线的票:{len(syms)} 只(已知数 300)")
    pool = load_pool()
    print(f"池子行数:{len(pool)}(已知数 74,268)✓")
    cids = resolve_company_ids(pool, syms)
    miss = [s for s, c in cids.items() if not c]
    print(f"在池子里找不到 company_id 的:{len(miss)} 只 → {miss}")
    mem = membership(pool, cids)
    mem.to_csv(os.path.join(HERE, "pool_membership_300.csv"), index=False)
    ss = scope_sets(mem)
    for k, v in ss.items():
        print(f"  {k}: 在口径内 {len(v)} 只 / 被排除 {len(syms)-len(v)} 只")
    print("筛选条件那一行:", SCOPE_FILTER_LINE)
