# -*- coding: utf-8 -*-
"""★★★★★ 《139》赛道基准 · **每年重定 vs 每季重定** 同一轮对照 —— ★ 只读面板，**不跑回测**。

★★★ 本文件 = probe/赛道基准_1108/算赛道_1108.py 的**逐行复制**，只改一件事：
  ★★ 重定日从「每年 1 月第一个交易日」改成「每季第一个交易日」，
  ★★★ 并在**同一轮、同一张面板、同一套覆盖层**上把两种口径都算出来
    —— ★★★★★ 这样「每年」那一版就是一道自证：它必须复现《133》第四节 D1 那六个数。

★★★ 判据、门槛、三种情形的处置：**全部写死在《139》第三/四节**（跑前已 commit）。
★ 不改 engine 一个字节（红线①）；不碰两路共用脚本（《131》教训）——
  ★★ probe/赛道基准_1108/ 里的两份原样不动。
"""
from __future__ import annotations
import importlib.util, json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT); sys.path.insert(0, ROOT)

PANEL = "probe/并池2004_1107/ohlcv_panel_newpool.parquet"
OUT = os.path.join(HERE, "赛道_季度对照_报告_1108.json")

窗口 = {"A_2004到2014": ("2004-01-02", "2014-12-31"),
       "B_2015到2025": ("2015-01-01", "2025-12-31")}
# ★★★ 《130》第七节那两个数 —— ★ 本脚本必须自己重算出同样的值（修订②的自证）
标普对账 = {"A_2004到2014": (7.82, 2768), "B_2015到2025": (13.47, 2765)}
成员下限 = 20          # ★ 一天不足 20 只 → 这一天不算（不填 0，《108》#73）
够格比例 = 0.60        # ★ 够格天数 < 60% → 整段不出数
年 = 252.0
# ★ 脏日判据照抄 扫假跳变_1107.py（三个阈值一字不改）
跳变门槛, 量反向容差, 窗 = 3.0, 1.5, 5
源跳门槛 = 50.0        # ★ 源头 warnings「无事件隔夜跳」≥50% 才算脏


def 载(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def 年化(x: pd.Series) -> float:
    x = pd.Series(x).dropna().astype(float)
    return float((1.0 + x).prod() ** (年 / len(x)) - 1.0)


# ══════════════════════════════════════════════════════ ① 面板身份指纹（规矩 70）
sys.path.insert(0, os.path.join(ROOT, "probe", "审计复核_1108"))
import 面板指纹_1108 as FP                                        # noqa: E402
指纹 = FP.必须是修接缝版(PANEL)
print("★★★ 面板指纹:", json.dumps(指纹, ensure_ascii=False), flush=True)

报 = {"★预先登记": "手册/139-跑前预先登记-赛道基准改成每季重定-1108.md（★ 判据与门槛跑前写死）",
     "★★★面板指纹": 指纹, "★★★自证": {}, "结果": {}}

# ══════════════════════════════════════════════════════ ② 读面板
t0 = time.time()
w = pd.read_parquet(PANEL)
cl, vol, dvv = w["close"], w["volume"], w["dollar_volume"]
del w
print(f"★ 面板 {cl.shape[1]} 只 × {cl.shape[0]} 天（{time.time()-t0:.0f}s）", flush=True)
报["★★★自证"]["面板形状"] = [int(cl.shape[0]), int(cl.shape[1])]

# ══════════════════════════════════════════════════════ ③ 两份脏日清单（现算，不手抄）
def 前中位(x):
    return x.shift(1).rolling(窗, min_periods=窗).median()


def 后中位(x):
    return x.iloc[::-1].rolling(窗, min_periods=窗).median().iloc[::-1]


pr = 后中位(cl) / 前中位(cl)
vr = 后中位(vol) / 前中位(vol)
疑 = (((pr >= 跳变门槛) & (vr <= 1 / 量反向容差)) |
     ((pr <= 1 / 跳变门槛) & (vr >= 量反向容差))).fillna(False)
我们扫 = 疑.to_numpy()
del pr, vr, vol
我们只数 = int((我们扫.any(axis=0)).sum()); 我们条数 = int(我们扫.sum())
print(f"★ 我们自己扫到：{我们只数} 只 / {我们条数} 个只×日", flush=True)

源 = 载("probe/假跳变_1107/并两份脏日重量_1107.py", "_dj")
os.chdir(ROOT)
源脏 = 源.源头脏日(源跳门槛)
列位 = {s: i for i, s in enumerate(cl.columns)}
日位 = {d: i for i, d in enumerate(cl.index)}
源命中 = np.zeros_like(我们扫)
源只, 源条 = set(), 0
for s, ds in 源脏.items():
    j = 列位.get(s)
    if j is None:
        continue
    for d in ds:
        i = 日位.get(pd.Timestamp(d))
        if i is not None:
            源命中[i, j] = True; 源只.add(s); 源条 += 1
print(f"★★★ 源头自己标的（落在本面板上的）：{len(源只)} 只 / {源条} 个只×日", flush=True)

脏 = 我们扫 | 源命中
报["★★★自证"]["脏日"] = {
    "★我们扫的": f"{我们只数} 只 / {我们条数} 个只×日（判据 价比≥{跳变门槛}倍 且 量反向≥{量反向容差}倍，前后各{窗}日中位）",
    "★★★源头自己标的": f"{len(源只)} 只 / {源条} 个只×日（warnings「无事件隔夜跳」≥{源跳门槛}%）",
    "★并集": f"{int(脏.any(axis=0).sum())} 只 / {int(脏.sum())} 个只×日",
    "★★注意": ("★ 这几个数**不等于**《92》零节③ 那个 553 只 / 1,651 只×日 —— "
             "★★ 那一份是在**老池 2,807 只**面板上扫的；★★★ 本份是在并池2004（3,858 只 × 22 年）上**现算**的。")}

# ══════════════════════════════════════════════════════ ④ 分红（全收益，和策略侧同口径）
sys.path.insert(0, os.path.join(ROOT, "probe", "并池_1107"))
from engine import data as edata                                  # noqa: E402

# ★★★★★ 规矩 67（#100 就是栽在这里）：跑批侧装过的覆盖层，**出数侧也要装同一套**。
#   ★ 第一次跑本脚本时我**只装了分红、没装基准** → ★★ A 段标普年化印成 +14.62%、
#     日数只有 251 天（2014 一整年）—— ★★★ 和《130》第九节 #100 **一模一样的错**。
#   ★★★ 是《132》修订② 那道「必须重算出 +7.82% / 2,768 天」的自证**当场把它挡下来的**
#     （规矩㊻：靠结构，不靠记性）。
BM = 载("probe/并池_1107/接新基准_1107.py", "_bm")
os.chdir(ROOT)
自证基准 = BM.install()
print("★★★ 基准覆盖层:", json.dumps(自证基准, ensure_ascii=False)[:500], flush=True)
assert 自证基准["★真的换掉了"], "★★★ 基准覆盖层没装上，停"
报["★★★自证"]["基准覆盖层"] = {"★★★基准自证": 自证基准["★★★基准自证"],
                        "★★★自动扫到的数据目录": 自证基准["★★★自动扫到的数据目录"]}
报["★★★自证"]["★★★没装哪些覆盖层_为什么"] = (
    "★ 本脚本**不跑引擎**（只读面板 + 算指数）→ 回看期 / 日序列 / 跳过基准一 / "
    "panel_meta 这四层对本脚本的数**一个都用不到**；★★ 用得到的两层（基准 BM · 分红 DV）"
    "都装了并各自落盘自证。★★★ 判法不是「我觉得用不到」，而是修订② 那道标普对账自证 ——"
    "少装一层它就对不上（实测：少装 BM → +14.62% / 251 天）。")

DV = 载("probe/并池_1107/分红覆盖层_1107.py", "_dv")
os.chdir(ROOT)
自证分红 = DV.install(需覆盖=sorted(cl.columns))
print("★★★ 分红覆盖层:", json.dumps(自证分红, ensure_ascii=False)[:600], flush=True)
报["★★★自证"]["分红"] = {k: 自证分红[k] for k in 自证分红
                     if k.startswith("★★★") or "覆盖" in k}
assert "0 只被折算过" not in 自证分红["★★★拆股折算生效"], "★★★ 折算没生效 —— 停跑"

div = {}
for s in cl.columns:
    d = edata.dividends(s)
    if len(d):
        div[s] = d
divm = pd.DataFrame(div).reindex(index=cl.index, columns=cl.columns).fillna(0.0)
print(f"★ 分红矩阵：{len(div)} 只有记录，非零格子 {int((divm > 0).to_numpy().sum())}", flush=True)
报["★★★自证"]["分红矩阵"] = {"有记录只数": len(div),
                       "非零分红格子": int((divm > 0).to_numpy().sum())}

prev = cl.shift(1)
R = (cl / prev - 1.0) + (divm / prev)      # ★★★ 和 全收益基准() 同一个公式
del divm, prev
Rv = R.to_numpy(); clv = cl.to_numpy()
有数 = np.isfinite(clv)
可算 = np.isfinite(Rv)

# ══════════════════════════════════════════════════════ ⑤ ADV60（面板现算，修订①）
# ★★★ 严格 PIT：60 个交易日均成交额，★ 再 shift(1) —— 重定日只用**昨天为止**已知的信息。
adv = dvv.rolling(60, min_periods=30).mean().shift(1).to_numpy()
del dvv

# ══════════════════════════════════════════════════════ ⑥ SPY 日集合 + 标普全收益自证
spy_nav = DV.全收益基准("SPY")

# ★★★ 策略侧年化：**照抄《130》第七节**（★ 那一份的数来自 出数_*_修分红_1108.json，
#   本脚本第四节已逐数核过尺子②）—— ★★ 本脚本不重跑回测，所以这里是**引用**，不是重算。
策略年化 = {"B_2015到2025": {"大波段技-1": 5.96, "突破技-6": 3.25, "震荡技-14": -5.74},
         "A_2004到2014": {"大波段技-1": -0.41, "突破技-6": 4.14, "震荡技-14": -5.46}}
Z130 = {"B_2015到2025": {"大波段技-1": -7.51, "突破技-6": -10.22, "震荡技-14": -19.21},
       "A_2004到2014": {"大波段技-1": -8.22, "突破技-6": -3.68, "震荡技-14": -13.28}}
曲线: dict[str, pd.Series] = {}

加权 = {"W1_成交额平方根": lambda a: np.sqrt(a),
       "W2_成交额": lambda a: a,
       "W3_等权": lambda a: np.where(np.isfinite(a), 1.0, np.nan)}


def 跑一段(窗名: str, 起: str, 止: str, 重定: str = "每年") -> dict:
    nav = spy_nav[(spy_nav.index >= pd.Timestamp(起)) & (spy_nav.index <= pd.Timestamp(止))]
    b = nav.pct_change().dropna()
    days = [d for d in b.index if d in 日位]
    ii = np.array([日位[d] for d in days])
    spy_r = b.reindex(days)
    spy年化 = 年化(spy_r) * 100
    期望年化, 期望天数 = 标普对账[窗名]
    对账 = {"★我重算的标普全收益年化": f"{spy年化:+.2f}%",
           "★《130》写的": f"{期望年化:+.2f}%",
           "★差": f"{spy年化-期望年化:+.3f}pp",
           "★我的天数": len(days), "★《130》的天数": 期望天数,
           "★★★对上了吗": ("✅ 逐数一致" if abs(spy年化 - 期望年化) < 0.005 and len(days) == 期望天数
                      else "⚠ 没完全对上 —— ★ 如实报，不去调日集合凑")}
    print(f"★★★ {窗名} 标普对账: {json.dumps(对账, ensure_ascii=False)}", flush=True)

    # ★★★ 重定日 —— ★ 《139》本轮唯一改的那一件：
    #   「每年」= 窗口第一天 + 每年 1 月第一个交易日（★ 《133》用的那一版）
    #   「每季」= 窗口第一天 + 每季第一个交易日（1/4/7/10 月）★★★ 《93》3.1/3.2 要的那一版
    rb = {0}
    di = pd.DatetimeIndex(days)
    yrs, qs = di.year, di.quarter
    for k in range(1, len(days)):
        if 重定 == "每年":
            if yrs[k] != yrs[k - 1]:
                rb.add(k)
        elif 重定 == "每季":
            if (yrs[k], qs[k]) != (yrs[k - 1], qs[k - 1]):
                rb.add(k)
        else:
            raise SystemExit(f"★★★ 重定口径只许 每年/每季，收到 {重定}")
    print(f"★ {窗名} · {重定}重定：重定日 {len(rb)} 个", flush=True)

    出 = {"★★★重定口径": 重定, "★重定日个数": None, "★★★标普对账": 对账, "★赛道": {}}
    曲线[f"{窗名}|SPY全收益|-|-"] = spy_r
    策普 = {k: v for k, v in 策略年化.get(窗名, {}).items()}
    出["★重定日个数"] = len(rb)
    出["★★★三段式"] = {}
    for wn, wf in 加权.items():
        for dn, 用脏 in (("D1_剔脏日", True), ("D0_不剔", False)):
            val = None
            rets, 够格 = [], 0
            for k, i in enumerate(ii):
                ok = 可算[i].copy()
                if 用脏:
                    ok &= ~脏[i]
                if k in rb or val is None:
                    base = wf(adv[i])
                    val = np.where(有数[i] & np.isfinite(base), np.nan_to_num(base), 0.0)
                m = ok & (val > 0)
                n = int(m.sum())
                if n >= 成员下限:
                    wsum = val[m].sum()
                    rets.append(float((val[m] * Rv[i][m]).sum() / wsum)); 够格 += 1
                else:
                    rets.append(np.nan)
                step = np.where(ok, 1.0 + np.nan_to_num(Rv[i]), 1.0)
                val = val * step
                val = np.where(有数[i], val, 0.0)        # ★ 退市：持到最后一个有价日，之后退出（收益已计）
            s = pd.Series(rets, index=days)
            曲线[f"{窗名}|{重定}|{wn}|{dn}"] = s
            if 够格 / len(days) < 够格比例:
                出["★赛道"][f"{wn}·{dn}"] = {"★算不出来": f"够格天数只有 {够格}/{len(days)}"}
                continue
            出["★赛道"][f"{wn}·{dn}"] = {
                "★★★赛道年化": f"{年化(s)*100:+.2f}%",
                "★★★Y_赛道减标普": f"{(年化(s)-年化(spy_r))*100:+.2f}pp/年",
                "★够格天数": f"{够格}/{len(days)}",
                "★日收益标准差": f"{float(s.std())*100:.3f}%"}
            print(f"   {窗名} {wn} {dn}: 年化 {年化(s)*100:+.2f}% · "
                  f"Y {(年化(s)-年化(spy_r))*100:+.2f}pp", flush=True)
            if dn != "D1_剔脏日":
                continue
            赛 = 年化(s) * 100; 普 = 年化(spy_r) * 100
            for 族, 策 in 策普.items():
                X, Y, Z = 策 - 赛, 赛 - 普, 策 - 普
                出["★★★三段式"][f"{族}·{wn}"] = {
                    "★X_赛道内我们赢没赢": f"{X:+.2f}pp/年",
                    "★★★X的检验": "**待配对检验**（★ 本轮没有策略日净值；★★★ 不许写「更好」也不许写「分不出」）",
                    "★Y_赛道减标普": f"{Y:+.2f}pp/年",
                    "★Z_整体减标普": f"{Z:+.2f}pp/年",
                    "★★★恒等式自证_X加Y减Z": f"{X + Y - Z:+.6f}pp（★ 必须 ≈0）",
                    "★Z对账_《130》写的": f"{Z130.get(窗名, {}).get(族, float('nan')):+.2f}pp/年"}
    return 出


for 窗名, (起, 止) in 窗口.items():
    报["结果"][窗名] = {}
    for 重定 in ("每年", "每季"):
        报["结果"][窗名][重定] = 跑一段(窗名, 起, 止, 重定)

# ★★★ 日序列落盘 —— ★ 后面补配对检验（策略日净值 vs 赛道指数）要用它。
曲线表 = pd.DataFrame(曲线)
曲线表.to_parquet(os.path.join(HERE, "赛道日收益_季度对照_1108.parquet"))
报["★★★自证"]["日序列落盘"] = {"列数": int(曲线表.shape[1]), "行数": int(曲线表.shape[0]),
                        "文件": "probe/赛道季度_1108/赛道日收益_季度对照_1108.parquet"}

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(报, fh, ensure_ascii=False, indent=1)
print("★ 写出:", OUT, flush=True)
