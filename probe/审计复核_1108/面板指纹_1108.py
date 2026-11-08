# -*- coding: utf-8 -*-
"""★★★★★ 面板身份指纹 —— ★ 回答「我手上这张面板是**哪一张**」（规矩 70 / 账本 #101）。

★★ 为什么要它：面板在 `.gitignore` 里，**每个容器自己烤** →
  ★★★ 1108 两路就栽在这儿：代码一样、自证全过、数对不上，
    因为一边是修接缝那张、一边是假接缝那张（全文《131》）。
★ 现有自证挡不住：第五个登记点（panel_meta）只证明「指针换掉了、3858 行」。

★★★ 用法（两种都行，都是现算，约 2~4 秒）：
    python3 probe/审计复核_1108/面板指纹_1108.py            # ★ 命令行，退出码 0=对 / 1=不对
    from 面板指纹_1108 import 指纹, 必须是修接缝版          # ★★ 跑批里一行断言

★★ `必须是修接缝版()` 不通过就 **raise** —— ★★★ 跑错面板不如不跑。
"""
from __future__ import annotations
import json, os, sys

_默认 = "probe/并池2004_1107/ohlcv_panel_newpool.parquet"
# ★★★ 判据来自《126》3.1 的自证（今早 A 路修接缝时量的），★ 不是我现编的
_应当 = {"跨2016-01-04价比异常只数": 0, "AAPL_2015-12-31": 26.32, "AAPL_2016-01-04": 26.34}


def 指纹(panel: str = _默认) -> dict:
    import pyarrow.parquet as pq
    f = pq.ParquetFile(panel)
    ix = f.schema_arrow.pandas_metadata["index_columns"]
    cl = [n for n in f.schema_arrow.names if n.startswith("('close'")]
    t = f.read(columns=cl + ix).to_pandas()
    t.columns = [c[1] for c in t.columns]
    r = t.loc["2016-01-04"] / t.loc["2015-12-31"]
    坏 = r[(r > 1.8) | (r < 0.55)]
    出 = {
        "面板": panel,
        "形状": [int(t.shape[0]), int(t.shape[1])],
        "跨2016-01-04价比异常只数": int(len(坏)),
        "异常里最离谱的三只": 坏.abs().sort_values(ascending=False).head(3).round(3).to_dict(),
        "AAPL_2015-12-31": round(float(t["AAPL"].loc["2015-12-31"]), 2),
        "AAPL_2016-01-04": round(float(t["AAPL"].loc["2016-01-04"]), 2),
    }
    对 = (出["跨2016-01-04价比异常只数"] == _应当["跨2016-01-04价比异常只数"]
         and abs(出["AAPL_2015-12-31"] - _应当["AAPL_2015-12-31"]) < 0.02
         and abs(出["AAPL_2016-01-04"] - _应当["AAPL_2016-01-04"]) < 0.02)
    出["★★★是修接缝版吗"] = 对
    出["★判据"] = (f"异常只数必须 0（★ 假接缝那张是 100 只）· "
                f"AAPL 必须 {_应当['AAPL_2015-12-31']} / {_应当['AAPL_2016-01-04']}"
                f"（★★ 假接缝那张是 105.26 / 26.34）—— 出处《126》3.1")
    return 出


def 必须是修接缝版(panel: str = _默认) -> dict:
    出 = 指纹(panel)
    if not 出["★★★是修接缝版吗"]:
        raise AssertionError(
            "★★★★★ 面板不是修接缝那张 —— 停跑。★ 现在手上这张："
            f"异常 {出['跨2016-01-04价比异常只数']} 只 · "
            f"AAPL {出['AAPL_2015-12-31']} / {出['AAPL_2016-01-04']}。"
            "★★ 重烤：python3 probe/基本面跑批_1106/烤并池2004修接缝_A路_1108.py"
            "（约 2 分 20 秒），★★★ 烤完把 parquet 拷到 probe/并池2004_1107/。全文《131》。")
    return 出


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else _默认
    if not os.path.exists(p):
        print(f"★★★ 面板不在：{p}  → ★ 先烤（《131》第四节第①步）"); raise SystemExit(2)
    出 = 指纹(p)
    print(json.dumps(出, ensure_ascii=False, indent=1))
    raise SystemExit(0 if 出["★★★是修接缝版吗"] else 1)
