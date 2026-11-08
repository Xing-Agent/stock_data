# -*- coding: utf-8 -*-
"""
★ 每条策略的可跑率(《99》3.4 第 2 条)—— ★ 一条策略一个子进程(一次算完全部会 OOM,1108 早实测)。
  可跑率 = 「大+中」口径在场票日里,这条策略要用的零件**全部算得出**的比例。
  单个零件的算得出比例见 覆盖率_单零件_2009.txt(覆盖率_1107.py 打出来的那一段)。
★★★ 「算不出」(零件 NaN)≠「算得出但没过闸」—— 本表只量前者。
"""
import io, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "可跑率_2009.json")


def 一条(name):
    import 覆盖率_1107 as C, 跑基本面_2009 as R2, 跑基本面_1106 as R0
    RC, _ = R2.装层()
    from engine import fundamentals as F, cache
    syms = list(cache._PANEL["close"].columns)
    close = cache.field("close", syms)
    mask, _ = RC.scope_mask(syms, close.index, R0.SCOPE)
    在 = (mask & close.notna()).loc[R2.PERF_START:]
    分母 = int(在.to_numpy().sum())
    全 = 在.copy()
    for z in C.零件[name]:
        p = F.get(z, syms).reindex(index=close.index, columns=syms).loc[R2.PERF_START:]
        全 &= p.notna()
        del p
        F.panel.cache_clear()
    return {"零件": C.零件[name], "分母票日": 分母,
            "★可跑率pct": round(float(全.to_numpy().sum()) / 分母 * 100, 1)}


if __name__ == "__main__":
    os.chdir(ROOT)
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        print(json.dumps(一条(sys.argv[2]), ensure_ascii=False)); raise SystemExit(0)
    import 覆盖率_1107 as C
    rep = json.load(io.open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    for name in C.零件:
        if name in rep:
            continue
        r = subprocess.run([sys.executable, __file__, "--one", name], capture_output=True, text=True)
        line = [x for x in r.stdout.splitlines() if x.startswith("{")]
        rep[name] = json.loads(line[-1]) if line else {"★★★跑失败": f"退出码 {r.returncode}: {r.stderr[-300:]}"}
        io.open(OUT, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=1))
        print(name, rep[name], flush=True)
