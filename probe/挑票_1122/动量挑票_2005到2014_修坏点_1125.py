#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《402》套数据组 11-23 的修正重跑（引擎不动：只在本进程里改内存中的行情面板，修法同 probe/成绩单_1122/跑手册全套_修坏点_1123.py）。
输出到 out_修/，文件名和原来一样，可断点续跑。约 180 处「待核」仍没动。"""
import io, os, sys, subprocess, json, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); FIX = os.path.join(ROOT, "probe/成绩单_1122")
if __name__ == "__main__":
    src = io.open(os.path.join(HERE, "动量挑票_2005到2014_1122.py"), encoding="utf-8").read().split('if __name__ == "__main__":')[0]
    a = 'OUT = os.path.join(HERE, "out")'; assert a in src; src = src.replace(a, 'OUT = os.path.join(HERE, "out_修")')
    hook = 'env = ENV.install(只留测试期=True); hs = env["留出池"]'; assert hook in src
    src = src.replace(hook, hook + f'\n    sys.path.insert(0, r"{FIX}"); import 跑手册全套_修坏点_1123 as _X; _log = _X.修面板(); print("修正", len(_log), flush=True)')
    g = {"__file__": os.path.join(HERE, "动量挑票_2005到2014_1122.py"), "__name__": "orig"}; exec(compile(src, "orig", "exec"), g); OUT = g["OUT"]; os.makedirs(OUT, exist_ok=True)
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        名 = sys.argv[2]; t = time.time()
        try: rec = g["跑一条"](名)
        except Exception as e: rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2000:]}
        rec["秒"] = round(time.time() - t, 1)
        json.dump(rec, io.open(os.path.join(OUT, f"结果_{名}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, rec["秒"], flush=True); sys.exit(0)
    for n in g["名单"]:
        if os.path.exists(os.path.join(OUT, f"结果_{n}.json")): continue
        subprocess.run([sys.executable, os.path.abspath(__file__), "--one", n])
    print("DONE")
