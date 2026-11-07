# -*- coding: utf-8 -*-
"""
★★★ 基-18 PEAD · **第 3 步「先只数次数」**（★ Lin 在《90》第四节定的次序，★★ 不是跳到跑收益）。

★★ Lin 的原话（《90》第四节第 3 步）：
   「★★★ **先只数次数** —— 研发池每季有多少只股票 SUE 进前 10%、分布在哪些年份。
     ★ **不看收益**。」

★★★ 为什么这一步可能**直接把这条策略否掉**（★ 《90》第五节已先写下来的风险）：
   ★ SUE 要 12 个季度 → ★★ 而财报只到 2009 年（SEC 结构化财报起点），
   ★★★ 回测窗口 2015~2025 → ★ 前几年会有一批票「期数不够被剔除」。
   → ★★ 如果某些年份每季只剩十几只 → ★★★ 那几年的结论**说明不了倾向**。

★ SUE 定义（★★ ①档 学术：Foster/Olsen/Shevlin 1984 · Bernard & Thomas 1989）：
   SUE = (本季每股收益 − 去年同季每股收益) ÷ 过去 **8 个**这种同比差值的标准差
★★★ 口径（★ 《90》第三节查实的，不是记的）：
   · 库里**只有稀释** `DilutedEPS`，**没有基本每股收益** → ★★ 一律用稀释并标明
   · 时点一律用 `Obs.eff`（★★★ = 申报日 + 1 个交易日，引擎已算好）—— ★ 严禁用 period_end
   · 8 个差值不满的公司**剔除**（★ 不用短窗口顶替）
"""
from __future__ import annotations
import glob, io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "probe", "补齐能力_1106"))
os.chdir(ROOT)
import 接新财报库_1106 as EXT                                    # noqa: E402
_EXT = EXT.install()
from engine import fundamentals as F                             # noqa: E402

HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
OUT = os.path.join(HERE, "先数次数_报告_1107.json")
分片 = os.path.join(HERE, "分片_1107")      # ★★★ 可续跑:每 100 只落一片
需要差值 = 8          # ★ 原著:过去 8 个同比差值
前百分比 = 10.0       # ★ 《90》骨架:前 10%
片大小 = 100
清缓存每 = 100        # ★★★ 每 100 只清一次 engine.fundamentals 的 lru_cache

# ★★★★★ 1107 第一次跑**被 OOM 杀了**(★ 2,224 只逐只算 SUE,到约 800 只时内存吃满,
#   ★★ 日志里连报错都没有 —— 被 SIGKILL,所以**看起来像卡住**)。
#   → ★ 两个修法(照《92》第四节的跑批纪律):
#     ① **每 100 只落一片**(`分片_1107/`)→ ★★ 重启能接上,不用从头
#     ② ★★★ **每 100 只清一次 `engine.fundamentals` 的 lru_cache** ——
#        ★ 它为了快把每只的季表都缓存着,★★ 2,224 只全缓存就是 7GB 打满的原因。


def 一只(sym: str) -> pd.DataFrame | None:
    """★ 返回 [eff, sue]；★★ 期数不够 → None（**剔除**，不猜）。"""
    try:
        obs = F.quarterly(sym, "DilutedEPS")
    except Exception:
        return None
    if not obs:
        return None
    s = pd.DataFrame({"eff": [o.eff for o in obs],
                      "pe": [o.period_end for o in obs],
                      "eps": [o.value for o in obs]}).dropna()
    if len(s) < 4 + 需要差值:          # ★ 至少 12 期才算得出第一个 SUE
        return None
    s = s.sort_values("pe").reset_index(drop=True)
    s["diff"] = s["eps"] - s["eps"].shift(4)                     # ★ 同比差值
    # ★★★ 标准差只用**过去** 8 个差值(含本季),★ 不含未来 —— min_periods 卡死
    sd = s["diff"].rolling(需要差值, min_periods=需要差值).std(ddof=1)
    s["sue"] = s["diff"] / sd.replace(0.0, np.nan)
    out = s.dropna(subset=["sue", "eff"])[["eff", "sue"]]
    return out if len(out) else None


def main() -> int:
    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev = list(hold["研发池名单"])
    留出 = set(hold["留出池名单"])
    assert not (set(dev) & 留出), "★ 研发/留出有交集，停"
    print(f"★ 研发池 {len(dev)} 只（★★ 只用研发池，考卷不碰）", flush=True)

    os.makedirs(分片, exist_ok=True)
    # ★★★ 续跑:先把已落盘的分片读回来
    行, 剔除, 做过 = [], [], set()
    for f in sorted(glob.glob(os.path.join(分片, "片_*.json"))):
        try:
            d0 = json.load(io.open(f, encoding="utf-8"))
        except Exception:
            continue
        做过 |= set(d0["做过"])
        剔除.extend(d0["剔除"])
        for sym, recs in d0["数"].items():
            行.append(pd.DataFrame({"eff": pd.to_datetime([x[0] for x in recs]),
                                    "sue": [x[1] for x in recs], "sym": sym}))
    待 = [s_ for s_ in dev if s_ not in 做过]
    print(f"★ 已做过 {len(做过)} 只（分片里读回来的）· 还要做 {len(待)} 只", flush=True)

    片数, 片剔, k0 = {}, [], 0
    for k, sym in enumerate(待):
        r = 一只(sym)
        if r is None:
            剔除.append(sym); 片剔.append(sym)
        else:
            r = r.copy(); r["sym"] = sym
            行.append(r)
            片数[sym] = [[str(a.date()), float(b)] for a, b in zip(r["eff"], r["sue"])]
        做过.add(sym)
        # ★★★ 每 清缓存每 只清一次缓存 —— ★ 这是上次被 OOM 杀的直接原因
        if (k + 1) % 清缓存每 == 0:
            for fn in (getattr(F, "quarterly", None), getattr(F, "ttm", None),
                       getattr(F, "quarter_frame", None), getattr(F, "panel", None),
                       getattr(F, "metric_quarterly", None),
                       getattr(F, "shares_quarterly", None)):
                if fn is not None and hasattr(fn, "cache_clear"):
                    fn.cache_clear()
        # ★★★ 每 片大小 只落一片(可续跑)
        if (k + 1) % 片大小 == 0 or k == len(待) - 1:
            io.open(os.path.join(分片, f"片_{len(做过):05d}.json"), "w",
                    encoding="utf-8").write(json.dumps(
                        {"做过": sorted(做过), "剔除": 片剔, "数": 片数},
                        ensure_ascii=False, default=str))
            print(f"   …{k+1}/{len(待)} · 落片(累计做过 {len(做过)})"
                  f" · 算得出 {len(行)} · 剔除 {len(剔除)}", flush=True)
            片数, 片剔 = {}, []

    报 = {"★口径": {
        "SUE": "(本季稀释每股收益 − 去年同季) ÷ 过去 8 个同比差值的标准差",
        "出处档": "★ ①档 学术 —— Foster/Olsen/Shevlin 1984 · Bernard & Thomas 1989",
        "每股收益": "★★★ 只有稀释 DilutedEPS（库里没有基本每股收益）—— 如实标明",
        "时点": "★★★ Obs.eff（= 申报日 + 1 个交易日）—— 严禁用 period_end",
        "期数不够": f"★ 不满 4+{需要差值}=12 期的公司**剔除**，不用短窗口顶替",
        "只用研发池": True,
        "★★★这一步不看收益": "★ 照 Lin《90》第四节第 3 步 —— 只数次数",
    }, "研发池只数": len(dev),
        "★算得出SUE的只数": len(行),
        "★★★期数不够被剔除": {"只数": len(剔除), "占比_pct": round(len(剔除)/len(dev)*100, 2),
                       "前5只": sorted(剔除)[:5]},
    }
    if not 行:
        报["★★★失败"] = "一只都算不出 —— **大声报，不许打空表**"
        io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
        print("★★★ 一只都算不出")
        return 1

    df = pd.concat(行, ignore_index=True)
    df["年"] = df["eff"].dt.year
    df["季"] = df["eff"].dt.to_period("Q").astype(str)

    # ★★ 每一个「申报季」内做横截面分位 → ★★★ 数进前 10% 的有多少只
    def 每季(g: pd.DataFrame) -> pd.Series:
        n = len(g)
        门 = g["sue"].quantile(1.0 - 前百分比 / 100.0)
        进 = int((g["sue"] >= 门).sum())
        return pd.Series({"当季有SUE的只数": n, f"进前{前百分比:.0f}%的只数": 进,
                          "门槛SUE": round(float(门), 3) if np.isfinite(门) else None})

    按季 = df.groupby("季", sort=True).apply(每季, include_groups=False).reset_index()
    按年 = df.groupby("年", sort=True).apply(每季, include_groups=False).reset_index()

    # ★ 只报绩效窗口(2015~2025)里的 —— ★★ 窗口外的不混进来
    按季窗 = 按季[按季["季"].str[:4].astype(int).between(2015, 2025)]
    按年窗 = 按年[按年["年"].between(2015, 2025)]

    报["按季"] = 按季窗.to_dict("records")
    报["按年"] = 按年窗.to_dict("records")

    少 = 按季窗[按季窗["当季有SUE的只数"] < 100]
    报["★★★样本不足的季（当季有 SUE 的不到 100 只）"] = {
        "季数": int(len(少)), "明细": 少.to_dict("records"),
        "★读法": "★★ 这些季的结论**说明不了倾向** —— ★★★ 不许只报全样本平均数（《90》第五节）",
    }
    头 = 按年窗.head(3).to_dict("records"); 尾 = 按年窗.tail(3).to_dict("records")
    报["★★前三年 vs 后三年"] = {"前三年": 头, "后三年": 尾,
        "★读法": "★ 《90》第五节预言「前几年明显偏少」—— ★★★ 这里逐条对"}

    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 写到 {OUT}")
    print(f"★ 算得出 {len(行)} 只 · 剔除 {len(剔除)} 只"
          f"（{len(剔除)/len(dev)*100:.1f}%）")
    print(f"★★ 样本不足的季：{len(少)} 个")
    print(按年窗.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
