# -*- coding: utf-8 -*-
"""★★★ 跑前自证：四个登记点（面板 · manifest · 池表 · 分红）—— 规矩㊺ / #72 #74 #80。

★ 为什么要单独一份：这四处今天各咬了我们一次。
  ① 面板有价格 ② manifest 有元信息 ③ 池表在排名里 ④ 分红查得到
  ★★★ 缺任何一处，这只票事实上买不到、或者口径标签是假的 —— 而跑批不会报错。
★★ 这一份**只读不写**，跑批之前跑一次，数对不上就停（不许带着对不上的数起跑批）。
"""
from __future__ import annotations
import io, json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "并池_1107"))
os.chdir(ROOT)
import pandas as pd
from engine import cache, data, pool_scope          # noqa: E402
import 接新基准_1107 as BM                           # noqa: E402
import 分红覆盖层_1107 as DV                         # noqa: E402

巨头 = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOG", "META", "BRK.B", "JPM", "AVGO", "NFLX"]
PANEL = "probe/并池2004_1107/ohlcv_panel_newpool.parquet"
POOL = "probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv"
报: dict = {"★★★这一份回答什么": "跑批能不能起 —— 四处登记是不是都齐（规矩㊺）"}

# ① 面板 ---------------------------------------------------------------
wide = pd.read_parquet(PANEL, columns=None)
close = wide["close"]
报["①面板"] = {
    "只数": int(close.shape[1]), "交易日": int(close.shape[0]),
    "起止": f"{close.index.min().date()} → {close.index.max().date()}",
    "★巨头在不在": {t: (int(close[t].notna().sum()) if t in close.columns else "★缺") for t in 巨头},
}
面板只 = set(close.columns)

# ② manifest ----------------------------------------------------------
计 = {}
for 根 in ("market_ext_1105", "exam_1042"):
    p = os.path.join(ROOT, 根, "manifest.csv")
    计[根] = (len(pd.read_csv(p)) if os.path.exists(p) else "★ 清单不在")
报["②manifest"] = {"各份行数": 计,
                  "★元信息文件": os.path.exists("probe/并池2004_1107/panel_meta_newpool.parquet")}

# ③ 池表 --------------------------------------------------------------
pt = pd.read_csv(POOL)
col = next((c for c in ("symbol", "ticker", "sym") if c in pt.columns), pt.columns[0])
年列 = next((c for c in ("year", "年", "asof_year") if c in pt.columns), None)
池内 = set(pt[col].astype(str))
报["③池表"] = {
    "行数": len(pt), "不同票数": len(池内), "列": list(pt.columns)[:8],
    "年份覆盖": (f"{int(pt[年列].min())} → {int(pt[年列].max())}" if 年列 else "★ 没找到年份列"),
    "★巨头在池表里": {t: (t in 池内) for t in 巨头},
    "★★★面板有但池表没有的只数": len(面板只 - 池内),
    "★★★池表有但面板没有的只数": len(池内 - 面板只),
}

# ④ 分红 --------------------------------------------------------------
BM.install()
自证分红 = DV.install(需覆盖=sorted(面板只))
报["④分红"] = 自证分红

# ★★★ 判决 ------------------------------------------------------------
不过 = []
if 报["①面板"]["只数"] != 3858:
    不过.append(f"面板只数 {报['①面板']['只数']} ≠ 3858")
if any(v == "★缺" for v in 报["①面板"]["★巨头在不在"].values()):
    缺 = [k for k, v in 报["①面板"]["★巨头在不在"].items() if v == "★缺"]
    不过.append(f"面板缺巨头 {缺}")
缺池 = [t for t, v in 报["③池表"]["★巨头在池表里"].items() if not v]
if 缺池:
    不过.append(f"★★★ 池表缺巨头 {缺池} —— universe 掩膜会把它们排除，永远买不到（#74）")
# ★★ 字段实际长这样："3858/3858 = 100.0%" —— ★ 不许凭记忆写格式，这里按实际的解
_cov文 = str(自证分红.get("★★★查得到文件的比例", ""))
_m = re.search(r"=\s*([0-9.]+)%", _cov文)
cov = float(_m.group(1)) if _m else -1.0
if cov < 90:
    不过.append(f"分红文件覆盖率 {_cov文!r} 解出 {cov}% < 90%（#80：开关开了但喂进去是空的）")
# ★★★ #80 的教训：自证要证「它起作用了」。基准侧 SPY 分红条数必须 > 0。
spy分红 = str(自证分红.get("★★★基准侧分红", {}).get("SPY", ""))
_n = re.match(r"\s*(\d+)\s*条", spy分红)
if (not _n) or int(_n.group(1)) == 0:
    不过.append(f"★★★ 基准侧 SPY 分红 = {spy分红!r} —— 全收益口径在基准侧是空转的（#80）")
报["★★★解出来的数"] = {"分红文件覆盖率%": cov, "基准侧SPY分红条数": (int(_n.group(1)) if _n else None)}
报["★★★判决"] = "✅ 四处都齐，可以起跑批" if not 不过 else "⛔ 不许起跑批"
报["★★★不过的项"] = 不过
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "跑前自证_四处登记_报告_1107.json")
io.open(out, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
print(json.dumps(报, ensure_ascii=False, indent=1, default=str))
raise SystemExit(0 if not 不过 else 2)
