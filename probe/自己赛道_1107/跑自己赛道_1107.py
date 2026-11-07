# -*- coding: utf-8 -*-
"""
★★★★★ 主基准：**自己赛道买入持有** —— ★ Lin 1107 13:05 定的，《93 比法规格书》第 3.1 节。

★★★ 他的原话：
  「我举个不做科技股的，做成长型医疗的基金，这两年收益率就是不如科技股。
    那你能跟大盘直接比吗？不能这么比。你得跟这个赛道里的『只买不动』比。」

★★ 落成能算的（★ 口径写死在这里 + 《92》二点二，两路一致）：
  · **赛道** = `engine.matrices.build(cfg.raw, dev).universe` ——
      ★ 这条策略自己 `universe` 段筛出来的那批票（流动性/股价/基本面闸门都算进去了）
  · **赛道指数** = 每天对「**前一天**在 universe 里」的票取**等权平均日收益**，复利成净值
      ★★★ 规矩㉙：资格用第 t 天收盘判，收益从 t 量到 t+1 → **不重叠一天**
  · **超额 + t** = ★★★ 把赛道净值**当 spy 传给** `新尺子_1106.一条指标()` ——
      ★ 复用同一段对数回归 + Newey-West，★★ **不另写统计**（免得两条基准口径不同）
  · **流水** = ★★ 剔脏日之后那一份（`probe/剔脏日重出_1107/ledgers_clean/`）

★★★★★ ⚠ 一处必须如实写明的口径差：
   ★ 赛道成员**每天在变**（票会进出 universe）→ ★★ 本份算的是「**赛道等权指数**」，
   ★★★ **不是**「第一天把当时合格的票买下来一直不动」。★ 两者不同；
   ★★ 选前者的理由：策略本身也是每天在变的池子里挑，★★★ 拿一个固定篮子比不同题。

★ 可续跑：**每条臂跑完立刻单独落盘**到 `arms/`，重跑时自动跳过已有的。
  用法：python3 probe/自己赛道_1107/跑自己赛道_1107.py [--max N]
"""
from __future__ import annotations
import gc, glob, importlib.util, io, json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
ARMS = os.path.join(HERE, "arms")
OUT = os.path.join(HERE, "自己赛道_报告_1107.json")
CLEAN = "probe/剔脏日重出_1107/ledgers_clean"
# ★★★★★ 1107 第 4 次唤醒**第二版**修的三处（★ 第一版出的数不能用，全文《108》）：
#   ① 赛道指数**没剔脏日** → 基-7 的「赛道」算出 **+242%/年**（VRDN +1328% 那种假跳变在里面）
#   ② 成员数为 0 的那些天我**悄悄填了 0.0 收益** → 基-1·回看10年 **3,018 天里 1,957 天**
#      是这么来的 → ★★★ 那不是基准，是我自己造的一条平线（规矩⑰ 原话管的正是这个）
#   ③ 没有**成员下限** → 一篮子 1~6 只微盘股**每天等权再平衡**，复利出来的数不是指数
最少成员 = 20          # ★ 一天不足这么多只 → 这一天**不算**（★★ 不是填 0）
最少覆盖 = 0.60        # ★★★ 够格的天数不到总天数这个比例 → **整条臂不出数**，如实写「赛道太小/太稀」
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"

_f = importlib.util.spec_from_file_location("_fund", "probe/基本面跑批_1106/跑基本面_1106.py")
FUND = importlib.util.module_from_spec(_f); _f.loader.exec_module(FUND)
_m = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(_m); _m.loader.exec_module(M)


def 安全名(s: str) -> str:
    return s.replace("/", "／").replace(" ", "_")


_脏缓存: dict = {}


def 脏格缓存(cl: pd.DataFrame) -> pd.DataFrame:
    """★★★ 和《93》《106》**完全同一个四份脏日并集** —— ★ 整轮只算一次，缓存起来。"""
    if "脏" in _脏缓存:
        return _脏缓存["脏"]
    sys.path.insert(0, os.path.join(ROOT, "probe/分档单调_1107"))
    _d = importlib.util.spec_from_file_location(
        "_dec", "probe/分档单调_1107/分档单调性_1107.py")
    DEC = importlib.util.module_from_spec(_d)
    _d.loader.exec_module(DEC)
    w = pd.read_parquet(PANEL)
    vol = w["volume"]
    del w
    脏 = DEC.脏格(cl, vol)
    del vol
    gc.collect()
    _脏缓存["脏"] = 脏
    return 脏


def 赛道指数(uni: pd.DataFrame, cl: pd.DataFrame, 脏: pd.DataFrame
             ) -> tuple[pd.Series | None, dict]:
    """★★★ 每天对「前一天在 universe 里、且这一天不脏」的票取等权平均日收益 → 复利成净值。
       ★★★★★ 够格天数不足 `最少覆盖` → **返回 None**，如实写「算不出」，★ 不许造一条平线。"""
    cols = [c for c in uni.columns if c in cl.columns]
    u = uni[cols].shift(1).fillna(False)          # ★★★ 规矩㉙：资格滞后一天
    # ★★★★★ 和《93》同一个四份脏日并集 —— ★ 脏格整格不参与赛道（第一版漏了这一步）
    z = 脏.reindex(index=u.index, columns=cols).fillna(False)
    u = u & (~z)
    r = cl[cols].pct_change().where(lambda x: np.isfinite(x))
    masked = r.where(u)
    n = masked.notna().sum(axis=1)
    够 = n >= 最少成员
    覆盖 = float(够.sum()) / len(n) if len(n) else 0.0
    diag = {"赛道成员数_中位": float(n.median()), "赛道成员数_最少": int(n.min()),
            "赛道成员数_最多": int(n.max()), "总天数": int(len(n)),
            "★★★成员数为0的天数": int((n == 0).sum()),
            f"★★★成员数≥{最少成员}的天数": int(够.sum()),
            "★★★覆盖率": round(覆盖, 4),
            "★★剔脏日剔掉的只×日": int((z & u.notna()).to_numpy().sum())}
    if 覆盖 < 最少覆盖:
        diag["★★★★★算不出"] = (f"★ 赛道一天够 {最少成员} 只的天数只占 {覆盖:.1%}"
                         f"（要 ≥{最少覆盖:.0%}）—— ★★★ **赛道太小/太稀，构不成一个指数**；"
                         f"★★ 不许用「成员数为 0 就填 0 收益」的办法凑（第一版就是这么错的）")
        return None, diag
    # ★ 只在够格的那些天上走净值；★★ 不够格的天**不计入**（不是填 0）
    d = masked.mean(axis=1, skipna=True).where(够)
    eq = (1.0 + d.dropna()).cumprod()
    return eq, diag


def main(argv) -> int:
    # ★★★★★ 实测：`matrices.build` 对一条基本面配置峰值 **~6.1GB**（dmesg 里被 OOM 杀过）
    #   → ★★ 所以**默认一条臂一个进程**，跑完就退，靠 `arms/` 落盘续上（配 重启循环_1107.sh）。
    上限 = 1
    if "--max" in argv:
        上限 = int(argv[argv.index("--max") + 1])
    os.makedirs(ARMS, exist_ok=True)
    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev = sorted(hold["研发池名单"])   # ★ matrices.build 要 list，不吃 set（规矩⑬ 那一类：先看它要什么）

    arms = FUND.臂表()
    做 = 0
    for arm in arms:
        名 = arm["臂"]
        fp = os.path.join(ARMS, 安全名(名) + ".json")
        if os.path.exists(fp):
            continue
        if 上限 is not None and 做 >= 上限:
            print(f"★ 到达本轮上限 {上限} 条，剩下的下一轮接着跑", flush=True)
            break
        t0 = time.time()
        rec = {"臂": 名, "配置": arm["配置"], "覆盖": arm["覆盖"], "档": arm.get("档", "")}
        try:
            RC, 层 = FUND.装层()
            from engine import matrices
            import yaml
            raw = yaml.safe_load(io.open(os.path.join(
                os.path.dirname("probe/基本面跑批_1106/configs/"), "configs", arm["配置"]),
                encoding="utf-8")) if False else yaml.safe_load(
                io.open(os.path.join("probe/基本面跑批_1106/configs", arm["配置"]),
                        encoding="utf-8"))
            for k, v in (arm["覆盖"] or {}).items():
                FUND._设(raw, k, v)
            # ★★★★★ 直接调 `universe_mask`，**不走 `build`** —— ★ 两条理由，都是查代码得来的：
            #   ① `engine/matrices.py:1276` 里 `build()` 自己就是 `uni = universe_mask(uni_spec, symbols)`
            #      → ★★ 所以这两条路拿到的 universe **是同一个函数的同一个返回值**，不是近似。
            #   ② `build()` 还要算 ATR / chandelier / rs_rank / entry / exit… ★★★ 实测一条臂 **272 秒**，
            #      而这些我**一个都不用**。→ ★ 只调 universe_mask。
            #   ★★ 另：`m.universe` 是 **ndarray**（不是 DataFrame，`Matrices` 那个 dataclass 里写着），
            #      而 `universe_mask()` 直接返回带 index/columns 的 DataFrame —— 正是我要的形状。
            uni = matrices.universe_mask(raw.get("universe") or {}, dev)
            matrices._DISABLED_LOG.clear()
            gc.collect()
            # ★ close 面板放到这里才读（★★ 和 matrices 的峰值**不重叠**）
            w = pd.read_parquet(PANEL)
            cl = w["close"]
            del w
            gc.collect()
            from engine import data as edata
            spy = edata.load_benchmark("SPY")["close"]
            脏 = 脏格缓存(cl)
            eq赛, diag = 赛道指数(uni, cl, 脏)
            del uni
            gc.collect()
            rec["★赛道诊断"] = diag
            if eq赛 is None:
                rec["★跑失败"] = diag["★★★★★算不出"]

            lp = os.path.join(CLEAN, f"REAL__{安全名(名)}.csv")
            if eq赛 is None:
                pass                       # ★ 赛道算不出 → 上面已登记，这条臂不出数
            elif not os.path.exists(lp):
                rec["★跑失败"] = f"找不到剔脏日后的流水 {lp}"
            else:
                d = pd.read_csv(lp)
                for c in ("entry_date", "exit_date"):
                    d[c] = pd.to_datetime(d[c], errors="coerce")
                for c in ("net_pnl", "shares", "entry_price", "notional_in"):
                    if c in d.columns:
                        d[c] = pd.to_numeric(d[c], errors="coerce")
                d = d.dropna(subset=["entry_date", "net_pnl"])
                if len(d) < 10:
                    rec["★跑失败"] = f"剔脏日后只剩 {len(d)} 笔 —— 样本太少，不出数"
                else:
                    eq, 在场, _ = M.逐日净值(d, cl)
                    win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
                    e = eq.loc[win]
                    z = 在场.loc[win]
                    # ★★★ 主基准：把赛道净值当 spy 传进去（复用同一段回归 + NW）
                    主 = M.一条指标(e, z, eq赛.reindex(e.index).ffill())
                    副 = M.一条指标(e, z, spy.reindex(e.index).ffill())
                    rec["★★★①主基准_对自己赛道"] = {
                        "alpha年pct": 主.get("★★★⑧alpha年化pct"),
                        "★★★alpha_t_NW": 主.get("★★★⑧alpha_t_NeweyWest"),
                        "beta_对赛道": 主.get("⑧beta_对SPY"),
                        "信息比率_对赛道": 主.get("★★★⑦信息比率_对SPY"),
                    }
                    rec["★★②副基准_对满仓SPY"] = {
                        "alpha年pct": 副.get("★★★⑧alpha年化pct"),
                        "★★★alpha_t_NW": 副.get("★★★⑧alpha_t_NeweyWest"),
                        "beta_对SPY": 副.get("⑧beta_对SPY"),
                    }
                    rec["★策略自己"] = {
                        "年化pct": 副.get("②年化收益pct"),
                        "最大回撤pct": 副.get("★★★③最大回撤pct"),
                        "卡玛": 副.get("★★★④卡玛比率"),
                        "平均投入pct": 副.get("★★★⑨平均投入比例pct"),
                        "笔数": int(len(d)),
                    }
                    # ★ 赛道本身长什么样（★★ 必须报 —— 否则看不出「赛道本来就难」）
                    # ★ 赛道净值现在**比策略短**（不够格的天不计入）→ ★★ 不能再用 eq 的 win 掩码
                    es = eq赛.loc[(eq赛.index >= M.PERF0) & (eq赛.index <= M.PERF1)]
                    yrs = (es.index[-1] - es.index[0]).days / 365.25
                    rec["★★★赛道自己"] = {
                        "年化pct": round(float(es.iloc[-1] / es.iloc[0]) ** (1 / yrs) * 100 - 100, 3)
                        if yrs > 0 else None,
                        "最大回撤pct": round(float((es / es.cummax() - 1).min()) * 100, 2),
                    }
        except Exception as e:
            rec["★跑失败"] = f"{type(e).__name__}: {str(e)[:300]}"
        rec["耗时秒"] = round(time.time() - t0, 1)
        io.open(fp, "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        做 += 1
        主 = rec.get("★★★①主基准_对自己赛道") or {}
        print(f"{'✗' if '★跑失败' in rec else '✓'} {名[:32]:32s} "
              f"赛道alpha {主.get('alpha年pct')} t={主.get('★★★alpha_t_NW')} "
              f"| {rec.get('★跑失败','')[:60]} ({rec['耗时秒']}s)", flush=True)

    # ---------------- 汇总 ----------------
    recs = [json.load(io.open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(ARMS, "*.json")))]
    ok = [r for r in recs if "★跑失败" not in r]
    def 显(向):
        return sorted(r["臂"] for r in ok
                      if isinstance((r.get("★★★①主基准_对自己赛道") or {}).get("★★★alpha_t_NW"), (int, float))
                      and ((r["★★★①主基准_对自己赛道"]["★★★alpha_t_NW"] >= 1.96) if 向 > 0
                           else (r["★★★①主基准_对自己赛道"]["★★★alpha_t_NW"] <= -1.96)))
    rep = {
        "★★★这一份是什么": "主基准（自己赛道买入持有）—— ★ 《93 比法规格书》第 3.1 节，Lin 1107 13:05 定",
        "★口径": {
            "赛道": "engine.matrices.build(cfg.raw, 研发池).universe —— 策略自己 universe 段筛出来的那批",
            "赛道指数": "每天对**前一天**在 universe 里的票取等权平均日收益，复利成净值",
            "★★★★★滞后(规矩㉙)": "资格用第 t 天收盘判，收益从 t 量到 t+1 —— 不重叠一天",
            "超额与t": "★★★ 把赛道净值当 spy 传给 新尺子_1106.一条指标() —— 复用同一段回归 + Newey-West",
            "流水": "剔脏日之后那一份（probe/剔脏日重出_1107/ledgers_clean/）",
            "★★★★★一处口径差要如实写明": "赛道成员每天在变 → 这是「赛道等权指数」，"
                               "**不是**「第一天买下来一直不动」；"
                               "★ 选前者因为策略本身也是在每天变的池子里挑",
            "窗口": f"{M.PERF0.date()} → {M.PERF1.date()}",
            "池子": "研发池 2,224 只（留出池和考卷不碰）",
        },
        "进度": {"臂总数": len(FUND.臂表()), "已跑": len(recs), "出数": len(ok),
               "失败": len(recs) - len(ok)},
        "★★★对自己赛道_正显著": 显(+1),
        "★★★对自己赛道_负显著": 显(-1),
        "逐臂": {r["臂"]: r for r in recs},
    }
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 已跑 {len(recs)}/{len(FUND.臂表())}；出数 {len(ok)}")
    print(f"★★★ 对自己赛道正显著: {显(+1) or '**一条都没有**'}")
    print(f"★★★ 对自己赛道负显著: {显(-1) or '**一条都没有**'}")
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
