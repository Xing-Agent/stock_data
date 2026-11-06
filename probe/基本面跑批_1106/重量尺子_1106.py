# -*- coding: utf-8 -*-
"""
★★ 流水不动、只重新量尺子 —— 主路 1106 21:45 修了大盘替身(当天进当天出被整笔扔掉 + 开盘/收盘没对齐),
   ★ 本路 33 条臂是修前量的 → 全部重量。★ 直接 import 仓库里最新那三份的「一条()」,不改它们。
"""
import glob, io, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); os.chdir(ROOT)
for d in ("probe/大盘替身_1106", "probe/尺子C_1106", "probe/账户百分比_1106"):
    sys.path.insert(0, os.path.join(ROOT, d))
import 大盘替身_1106 as B, 尺子C_1106 as C, 按净值百分比_1106 as A   # noqa: E402
ver = subprocess.run(["git", "log", "-1", "--format=%h %s", "--", "probe/大盘替身_1106/大盘替身_1106.py"],
                     capture_output=True, text=True).stdout.strip()
for f in sorted(glob.glob(os.path.join(HERE, "arms", "*.json"))):
    r = json.load(io.open(f, encoding="utf-8"))
    if "★★★跑失败" in r:
        continue
    lp = os.path.join(HERE, "ledgers", f"REAL__{r['臂'].replace('/', '／').replace(' ', '_')}.csv")
    for 名, M in (("★★★大盘替身(主判据)", B), ("尺子C(只量进场)", C), ("账户百分比(给用户看)", A)):
        try:
            r[名] = M.一条(lp) if r.get("笔数") else {"★算不出": "0 笔"}
        except Exception as e:
            r[名] = {"★跑失败": f"{type(e).__name__}: {str(e)[:300]}"}
    r["★尺子版本"] = f"大盘替身 = {ver}"
    io.open(f, "w", encoding="utf-8").write(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    print("✓", r["臂"], r["★★★大盘替身(主判据)"].get("★★★④差(真 减 替身)pct"),
          r["★★★大盘替身(主判据)"].get("t值"), flush=True)
