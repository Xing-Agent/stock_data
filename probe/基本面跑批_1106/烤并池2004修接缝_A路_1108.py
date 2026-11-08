# -*- coding: utf-8 -*-
"""
★★★★★ 并池2004 面板在 **2015-12-31 → 2016-01-04 有一条假接缝**:100 只票价格一夜跳几倍到几百倍。

★ 三秒版:同一只票的两段数据(2004~2015 一段、2016 起一段)是**各自**做的拆股修正 ——
  ★★ 2016 以后的拆股(苹果 2020 年 1 拆 4)只记在后一段的原始行里,前一段**不知道** →
  ★★★ 前一段没被除以 4,后一段被除了 → 拼起来苹果 2015-12-31 收 105.26、2016-01-04 收 26.34。

★★ 实测(主路烤出来的 probe/并池2004_1107/ohlcv_panel_newpool.parquet):
  跨这一天价格比 > 1.8 或 < 0.55 的有 **100 只**:
  CMG ×0.02 · AMZN ×0.05 · NFLX ×0.10 · AVGO ×0.10 · AAPL ×0.25 · … · SIRI ×9.7 · RAD ×20 · NBR ×51 · CHK ×220
  ★ 根因在 `probe/并池_1107/烤并池_1107.py` 的 `读日线接起来`:逐段调原读法(每段各自 `_apply_split_fix`)再拼。
★★★ 影响:所有用这张 2004 面板、持仓或指标跨过 2016 年初的结果(★ 三路都用它)。
  ★ 比如 A 路 基-5 德雷曼 71.8% 的总盈亏来自可疑笔,其中好几笔正好在 2016-01-05 前后出场。

★★ 修法(只在本路目录,不改主路文件):**先把各段的原始行按日期合并,再做一次拆股修正**
  (★ 和单段读法完全同一个函数 `engine.data._apply_split_fix`,只是喂给它的 raw_rows 是合并后的全量)。
  其余照用主路那份的四处覆盖(目录表 / 两份 manifest / 不排除考卷 / 基准 2004)。
★ 输出到本目录 并池2004修接缝_1108/(★ 465MB,不入库;本脚本约 3 分钟可复现)。
★ 自证:跑完重算「跨 2016-01-04 价比异常」只数,写进报告。
"""
import gzip, json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "并池_1107"))
os.chdir(ROOT)
import 烤并池_1107 as P                       # noqa: E402
from engine import data as edata             # noqa: E402

OUT = os.path.join(HERE, "并池2004修接缝_1108")


def 合并读(path: str, symbol: str) -> pd.DataFrame:
    cands = P._DIRS.get(symbol) or [path]
    by_date = {}
    for p in cands:                                    # ★ 同拼接口径:重复日期保留后读到的那段
        op = gzip.open if p.endswith(".gz") else open
        try:
            with op(p, "rt", encoding="utf-8") as fh:
                rows = json.load(fh).get("data") or []
        except (OSError, ValueError):
            continue
        for r in rows:
            by_date[str(r.get("date"))[:10]] = r
    rows = [by_date[k] for k in sorted(by_date)]
    cols = ["open", "high", "low", "close", "volume", "dollar_volume"]
    if not rows:
        return pd.DataFrame(columns=cols)
    # ★ 以下逐行照抄 烤新池_1106.读日线 —— 唯一差别:raw_rows 是**合并后的全量**
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    keep = ["open", "high", "low", "close", "volume"]
    for c in keep:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[keep].astype(float)
    df = df[~df.index.duplicated(keep="last")]
    df = edata._apply_split_fix(df, symbol, raw_rows=rows)
    df["dollar_volume"] = df["close"] * df["volume"]
    return df


def 自证(panel_path):
    import pyarrow.parquet as pq
    f = pq.ParquetFile(panel_path)
    ix = f.schema_arrow.pandas_metadata["index_columns"]
    cl = [n for n in f.schema_arrow.names if n.startswith("('close'")]
    t = f.read(columns=cl + ix).to_pandas()
    t.columns = [c[1] for c in t.columns]
    r = t.loc["2016-01-04"] / t.loc["2015-12-31"]
    x = r[(r > 1.8) | (r < 0.55)].sort_values()
    return {"跨2016-01-04价比异常只数": int(len(x)), "明细": x.round(3).to_dict(),
            "AAPL": t["AAPL"].loc["2015-12-28":"2016-01-08"].round(2).tolist()}


if __name__ == "__main__":
    t0 = time.time()
    B = P.B
    B.目录表 = P.目录表两处
    B.新manifest = P.manifest两处
    B.读日线 = 合并读                                 # ★★★ 唯一和主路不同的那一处
    证 = P.BM.install()
    spy = (证.get("★★★基准自证") or {}).get("SPY")
    assert spy and str(spy)[:10] <= "2004-12-31", f"★★★ SPY 还没拉到 2004:{spy}"
    B.考卷名单 = lambda: set()
    B.OUT = OUT
    os.makedirs(OUT, exist_ok=True)
    rc = B.main()
    前 = 自证("probe/并池2004_1107/ohlcv_panel_newpool.parquet") if os.path.exists(
        "probe/并池2004_1107/ohlcv_panel_newpool.parquet") else None
    后 = 自证(os.path.join(OUT, "ohlcv_panel_newpool.parquet"))
    rep = {"★修法": "先合并各段原始行,再做一次 _apply_split_fix", "修前(主路面板)": 前, "修后(本路面板)": 后,
           "耗时秒": round(time.time() - t0, 1)}
    json.dump(rep, open(os.path.join(HERE, "修接缝自证_1108.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "明细"})
                      for k, v in rep.items()}, ensure_ascii=False, indent=1))
    raise SystemExit(rc)
