"""量化:两窗口两池子硬关的随机种子不稳定性。
根因:window_pool.run_grid 的 seed = seed + hash((wname,pool)) % 10000,
      而 Python 的 hash() 对字符串逐进程随机 → 每次跑同一份代码、同一份数据,
      四格的 Z 和差值都不一样。"""
import sys, json
import numpy as np
sys.path.insert(0, "/home/claude/xing-agent-stock_data")
from engine import data, chain, stats_gate, window_pool, run_batch
from engine import run_gate_redesign as R

syms = [s.symbol for s in data.load_manifest().values()]
cfg = chain.ChainConfig.from_dict(R.build_variant("G0", 10, R.THR_MAIN, 0.5))

KEYS = ["2018-2021×池A", "2018-2021×池B", "2022-2025×池A", "2022-2025×池B"]
orig = window_pool.run_grid
rows = []
N = 10
for off in range(N):
    def patched(signal_fn, symbols, B=stats_gate.B_DEFAULT, seed=20181001, _o=off):
        cells = []
        for wname, wstart, wend in window_pool.WINDOWS:
            for pool in window_pool.POOLS:
                cs = window_pool.split_pool(symbols, pool)
                vals, samp = signal_fn(wstart, wend, cs)
                r = stats_gate.bootstrap_test(
                    name=f"{wname}×池{pool}", signal_values=vals,
                    random_sampler=samp, B=B,
                    seed=seed + (_o * 1009 + len(wname) * 37 + ord(pool[-1])) % 10_000,
                    note="同格内取样")
                cells.append(window_pool.CellResult(wname, pool, r))
        return window_pool.judge(cells)
    window_pool.run_grid = patched
    v = run_batch.window_pool_gate(cfg, syms)
    rows.append({"轮": off, "通过": bool(v.passed),
                 "n": [int(c.result.n_signal) for c in v.cells],
                 "Z": [round(float(c.result.z_effect), 3) for c in v.cells],
                 "差值": [round(float(c.result.diff), 4) for c in v.cells],
                 "降级结论": v.downgraded_conclusion})
window_pool.run_grid = orig

Z = np.array([r["Z"] for r in rows], float)
print(f"G0 slots10 —— {N} 次不同随机种子、同一份代码同一份数据下的四格 Z\n")
print(f"{'格子':18s} {'最小':>7s} {'最大':>7s} {'极差':>6s}  跨1.65  跨2.0  变号")
for i, k in enumerate(KEYS):
    c = Z[:, i]
    print(f"{k:18s} {c.min():+7.3f} {c.max():+7.3f} {c.max()-c.min():6.3f}"
          f"   {'★是' if c.min()<1.65<c.max() else ' 否'}"
          f"    {'★是' if c.min()<2.0<c.max() else ' 否'}"
          f"   {'★是' if c.min()<0<c.max() else ' 否'}")
print("\n每格笔数 n(应恒定,用来证明变的只是随机对照、不是成交):", rows[0]["n"])
print("十轮「通过」判定:", [r["通过"] for r in rows])
dc = sorted(set(r["降级结论"] or "(无)" for r in rows))
print(f"十轮产生了 {len(dc)} 种不同的「降级结论」文本:")
for d in dc:
    print("   -", d)
json.dump(rows, open("/tmp/claude-0/-home-claude/e6b5eede-2545-5921-9bbc-5820cecf2c9c/scratchpad/seed_stability.json","w"),
          ensure_ascii=False, indent=1)
