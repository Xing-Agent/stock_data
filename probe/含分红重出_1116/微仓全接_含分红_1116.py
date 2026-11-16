#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微仓全接诊断 · 含分红重出（2026-11-16 · Lin 拍板：分红口径统一成两侧都含分红）

大白话：和 probe/微仓全接_1114 一模一样，只多一件事 —— 策略这一侧把分红算进去。
做法：进程里装上补分红_1107，并把 data.TOTAL_RETURN_DEFAULT 在内存里设成 True。
engine/ 一个字节不改（只改内存里的开关，文件不动）。结果单独放本目录，不覆盖 1114 的不含分红版。
"""
import io, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe/微仓全接_1114"))
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
import 微仓全接_1114 as M
M.OUT = os.path.join(HERE, "微仓_out")
M.LED = os.path.join(HERE, "微仓_ledgers")


def 打补丁():
    import 跑基本面_1106 as B
    原 = B.装层
    def 装层含分红():
        r = 原()
        import 补分红_1107 as DIV
        DIV.install()
        from engine import data
        data.TOTAL_RETURN_DEFAULT = True
        return r
    B.装层 = 装层含分红


def main(argv):
    os.makedirs(M.OUT, exist_ok=True)
    if "--one" in argv:
        打补丁()
        名 = argv[argv.index("--one") + 1]
        item = next(x for x in M.清单() if x["名"] == 名)
        try:
            rec = M.跑一条(item)
            rec["分红"] = "策略侧含分红"
        except Exception as e:
            import traceback
            rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2500:]}
        io.open(M.出文件(名), "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    for it in M.清单():
        if os.path.exists(M.出文件(it["名"])):
            continue
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", it["名"]], cwd=ROOT)
        if not os.path.exists(M.出文件(it["名"])):
            io.open(M.出文件(it["名"]), "w", encoding="utf-8").write(json.dumps(
                {"名": it["名"], "跑失败": f"子进程退出码 {r.returncode}"}, ensure_ascii=False))
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
