#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐步量 matrices.build 的内存（2026-11-13）

为什么要量：Matrices 的最终输出只有约 0.6GB（12 张 float 表 + 5 张 bool 表），
但 build 在 8GB 机器上被杀。说明吃内存的是中间量，不是结果。
本脚本把 build 里的每一步单独跑一遍，每步之后记峰值内存，
进程死在哪一步、哪一步涨得最多，一目了然。

每一行都立刻落盘（flush + fsync）—— 进程被杀时日志还在。
只调用 engine 的函数，不改 engine/ 一个字节。
"""
import copy
import gc
import io
import json
import os
import resource
import sys
import time

ROOT = "/home/claude/xing-agent-stock_data"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
LOG = os.path.join(ROOT, "probe/分批build_1113/逐步量内存_日志.txt")
_f = io.open(LOG, "w", encoding="utf-8")


def 峰值():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def 当前():
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) // 1024
    return -1


def 记(msg):
    s = f"[{time.strftime('%H:%M:%S')}] 当前 {当前():5d}MB · 峰值 {峰值():5d}MB · {msg}"
    print(s, flush=True)
    _f.write(s + "\n")
    _f.flush()
    os.fsync(_f.fileno())


def main():
    import yaml
    import 跑基本面_1106 as B
    from engine import chain, matrices as M, data, cache

    臂号 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev = hold["研发池名单"]
    记(f"import 完 · 研发池 {len(dev)} 只")
    RC, info = B.装层()
    记("装层完")
    arm = B.臂表()[臂号]
    raw = copy.deepcopy(yaml.safe_load(io.open(os.path.join(B.CFG, arm["配置"]), encoding="utf-8")))
    for k, v in arm["覆盖"].items():
        B._设(raw, k, v)
    cfg = chain.ChainConfig.from_dict(raw).raw
    记(f"配置读完 · 臂 = {arm.get('臂')}")

    步 = []

    def 跑(名, fn):
        gc.collect()
        前 = 峰值()
        t0 = time.time()
        记(f"开始 → {名}")
        out = fn()
        形 = getattr(out, "shape", None)
        记(f"完成 ← {名} · 峰值涨了 {峰值() - 前}MB · {time.time() - t0:.1f}s · 形状 {形}")
        步.append((名, 峰值() - 前))
        return out

    uni_spec = cfg.get("universe") or {}
    uni = 跑("① universe_mask（选股范围）", lambda: M.universe_mask(uni_spec, dev))
    syms = list(uni.columns)
    记(f"选股范围之后剩 {len(syms)} 只 × {len(uni.index)} 天")
    跑("close 面板", lambda: cache.field("close", syms))
    跑("open/high/low 面板", lambda: (cache.field("open", syms), cache.field("high", syms),
                                    cache.field("low", syms))[0])
    reg = cfg.get("regime") or {}
    跑("② regime_mask（环境闸）", lambda: M.regime_mask(reg, uni.index, None, None))
    跑("③ entry_trigger（进场扳机）", lambda: M.entry_trigger(cfg.get("entry") or {}, syms))
    st = (cfg.get("trailing_stop") or {}).get("params", {}) or {}
    isp = (cfg.get("initial_stop") or {}).get("params", {}) or {}
    atr_p = int(isp.get("atr_period", st.get("atr_period", 20)))
    跑("atr_matrix", lambda: M.atr_matrix(atr_p, syms))
    跑("chandelier_raw_matrix", lambda: M.chandelier_raw_matrix(
        int(st.get("lookback", 22)), float(st.get("multiple", 3.0)), atr_p, syms))
    跑("adv_matrix(20)", lambda: M.adv_matrix(20, syms))
    跑("rs_rank_matrix（全池互相比）", lambda: M.rs_rank_matrix(
        int(uni_spec.get("rs_lookback", 126)), syms))
    跑("⑥ exit_signal_matrix", lambda: M.exit_signal_matrix(cfg.get("exit") or {}, syms))
    跑("⑥ fundamental_exit_matrix", lambda: M.fundamental_exit_matrix(cfg.get("exit") or {}, syms))
    跑("⑦ rank_score_matrix", lambda: M.rank_score_matrix(
        (cfg.get("sizing") or {}).get("rank_by"), syms, cfg))

    记("全部步骤单独跑完（没被杀）")
    记("各步峰值增量，从大到小：")
    for 名, d in sorted(步, key=lambda x: -x[1]):
        记(f"   {d:6d}MB  {名}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
