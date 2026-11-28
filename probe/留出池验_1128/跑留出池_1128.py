#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《517》留出池最后一次验 —— 技术类 34 个版本在留出池上两段各跑一遍。引擎外，engine/ 一个字节不改。
做法：读主 chat 的 probe/成绩单_1122/跑手册全套_1122.py 源码，只在内存里换四处（原文件不动）：
  ① 票池：研发池名单 → 留出池名单（probe/新策略_1106/holdout_newpool_1106.json 的「留出池名单」583 只；第二段取其中在 2004 面板上有数的）；
  ② 流动性池掩膜：原来读研发池那份文件；留出池没有现成的，用同一条规则现算（环境2004_1120.流动性池 那条：收盘 ≥5 美元、20 日均成交额 ≥1,000 万、满 60 天，季度调、留池缓冲 4 美元 / 0.8）；
  ③「留出池漏进来就报错」→ 反过来：「研发池漏进来就报错」；
  ④ 输出目录 → probe/留出池验_1128/out_留出池/（--池 研发 时 → out_研发池对账/，只用来核这套换法和原来的数对不对得上）。
第二段（2005–2014）照主 chat 2005–2014 那次，套 跑手册全套_修坏点_1123 的 修面板()。
用法：python3 跑留出池_1128.py --池 留出 [--段 一|二] [--只 技-1]     （一条策略一个子进程，可断点续跑）"""
import copy, io, json, os, subprocess, sys, time, traceback, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); SRC = os.path.join(ROOT, "probe/成绩单_1122")
HOLD = os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json")


def 掩膜(names, start, end):
    import numpy as np, pandas as pd
    from engine import cache
    close = cache._PANEL["close"][names].astype(float); vol = cache._PANEL["volume"][names].astype(float)
    adv = (close * vol).rolling(20, min_periods=20).mean(); bars = close.notna().cumsum()
    idx = close.index; perf = idx[(idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))]
    q = pd.Series(perf.quarter, index=perf); 调 = [perf[0]] + [d for d, a, b in zip(perf[1:], q.values[1:], q.values[:-1]) if a != b]
    mask = pd.DataFrame(False, index=perf, columns=names); 在 = np.zeros(len(names), bool)
    for k, d in enumerate(调):
        i = idx.get_loc(d); c, a, n = close.iloc[i - 1].to_numpy(), adv.iloc[i - 1].to_numpy(), bars.iloc[i - 1].to_numpy()
        进 = (c >= 5.0) & (a >= 1e7) & (n >= 60); 留 = (c >= 4.0) & (a >= 1e7 * 0.8) & (n >= 60)
        在 = np.where(在, 留, 进) & np.isfinite(c); end_ = 调[k + 1] if k + 1 < len(调) else None
        mask.loc[perf[(perf >= d) & ((perf < end_) if end_ is not None else True)]] = 在
    mask.loc[:, [c for c in ("TLN", "BTE", "SMCI", "GTX") if c in mask.columns]] = False      # 同 流动性池_1114 的 1118 补丁：中间断档 60 天以上又接上的四只
    return mask


def 载入(池):
    src = io.open(os.path.join(SRC, "跑手册全套_1122.py"), encoding="utf-8").read().split('if __name__ == "__main__":')[0]
    out = os.path.join(HERE, "out_留出池" if 池 == "留出" else "out_研发池对账")
    改 = [('OUT = os.path.join(HERE, "out_手册")', f'OUT = {out!r}'),
         # 第一段：票池 + 掩膜
         ('dev, hs = hold["研发池名单"], set(hold["留出池名单"])',
          ('dev, hs = hold["留出池名单"], set(hold["研发池名单"])' if 池 == "留出" else 'dev, hs = hold["研发池名单"], set(hold["留出池名单"])') + '; dev = [x for x in dev if x in cache._PANEL["close"].columns]'),
         ('mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet")); s, e = data.PERF_START, data.PERF_END',
          's, e = data.PERF_START, data.PERF_END; mk = _掩膜(dev, s, e)'),
         # 第二段：票池 + 修坏点 + 掩膜
         ('env = ENV.install(只留测试期=True); hs = env["留出池"]',
          'env = ENV.install(只留测试期=True); hs = env["留出池"]\n        import 跑手册全套_修坏点_1123 as _X; _log = _X.修面板(); print("修正", len(_log), flush=True)'),
         ('dev = [x for x in env["dev"] if bool(has.get(x, False))]',
          ('dev = sorted(x for x in hs if bool(has.get(x, False))); hs = set(env["dev"])' if 池 == "留出" else 'dev = [x for x in env["dev"] if bool(has.get(x, False))]')),
         ('mk = pd.read_parquet(os.path.join(W2, "流动性池掩膜2004_中.parquet")); s, e = ENV.START, ENV.END',
          's, e = ENV.START, ENV.END; mk = _掩膜(dev, s, e)'),
         ('if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("留出池漏进来")',
          'if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("另一个池子的票漏进来")\n    if len(L) and not set(L["symbol"].astype(str)) <= set(dev): raise RuntimeError("流水里有不在名单里的票")')]
    for a, b in 改:
        assert a in src, a[:70]; src = src.replace(a, b)
    g = {"__file__": os.path.join(SRC, "跑手册全套_1122.py"), "__name__": "orig", "_掩膜": 掩膜}
    sys.path.insert(0, SRC); sys.path.insert(0, ROOT); exec(compile(src, "orig", "exec"), g); return g


if __name__ == "__main__":
    a = sys.argv; 池 = a[a.index("--池") + 1] if "--池" in a else "留出"
    if "--one" in a:
        名, 段 = a[a.index("--one") + 1], a[a.index("--one") + 2]; g = 载入(池); os.makedirs(g["OUT"], exist_ok=True); t = time.time()
        try: rec = g["跑一条"](名, 段)
        except Exception as ex_: rec = {"名": 名, "段": 段, "跑失败": f"{type(ex_).__name__}: {ex_}", "traceback": traceback.format_exc()[-2000:]}
        rec["秒"] = round(time.time() - t, 1)
        json.dump(rec, io.open(os.path.join(g["OUT"], f"成绩单_{段}_{名}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
        print(("FAIL " if "跑失败" in rec else "ok   ") + 段, 名, rec["秒"], flush=True); sys.exit(0)
    段们 = [a[a.index("--段") + 1]] if "--段" in a else ["一", "二"]
    spW = importlib.util.spec_from_file_location("w2", os.path.join(ROOT, "probe/两段时间_1120/跑第二段_1120.py")); w2 = importlib.util.module_from_spec(spW); spW.loader.exec_module(w2)
    names = ["buy_and_hold"] + w2.名单()
    if "--只" in a: names = [a[a.index("--只") + 1]]
    out = os.path.join(HERE, "out_留出池" if 池 == "留出" else "out_研发池对账"); os.makedirs(out, exist_ok=True)
    for 段 in 段们:
        for n in names:
            if os.path.exists(os.path.join(out, f"成绩单_{段}_{n}.json")): continue
            subprocess.run([sys.executable, __file__, "--池", 池, "--one", n, 段])
    print("DONE")
