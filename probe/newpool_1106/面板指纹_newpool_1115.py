# -*- coding: utf-8 -*-
"""★★★★★ newpool 面板身份指纹 —— ★ 回答「我手上这张 newpool 面板是**哪一张**」。

★★ 为什么 1115 才补这个：★★★ 规矩 70 那套指纹（`probe/审计复核_1108/面板指纹_1108.py`）
  只管 **并池2004** 那张；★★★★★ **newpool 这张一个指纹检查都没有** —— 错号 #113
  （池子跨容器对不上）的三个可疑方向里，**第 ① 个就是它**（全文《194》四节 /《195》）。

★★★ 1115 查实的事（★ 只写查实的，不写推断）：
  · 面板**元信息**（`panel_meta_newpool.parquet`）在本容器重烤后与库里那份 **md5 完全相同**
    → ★ 票单子 / bar 数 / 退市结算价 **逐只一致**，`烤新池_报告` 只差一个「耗时秒」。
  · 池子报告 + 机会集宽基日净值：**1114 夜那个容器 与 1115 这个容器 md5 完全相同**
    → ★★★ 错号 #113 **不是「随机」也不是「容器漂移」**，两个独立容器**逐字节复现**。
  · 库里 B 路那份是**唯一的异类**（成分只数 821/604/337 · 中档卡玛 0.18），
    日净值从 **2015-01-05** 起分叉。★★ 分红登记点**不是原因**（两边都是 937 / 2224 只有分红记录）。

🔴 ★★★★★ 本文件登记的基线 = **1115 本容器实测值**。
  ★★ 它**不证明**「这一份对、B 路那份错」—— ★★★ 哪一份算官方是 Lin 的 DEC-新1，本文件不替他定。
  ★ 它只保证一件事：**以后任何容器拿这张面板出数之前，先知道自己拿的是哪一张。**

★★★ 用法（三种，都是现算）：
    python3 probe/newpool_1106/面板指纹_newpool_1115.py                 # ★ 退出码 0=对上基线 / 1=没对上
    from 面板指纹_newpool_1115 import 必须对上1115基线                  # ★★ 跑批里一行断言
    python3 probe/newpool_1106/面板指纹_newpool_1115.py --池 <报告.json>  # ★★★ 规矩 76 的池子指纹
"""
from __future__ import annotations
import hashlib, io, json, os, sys

面板 = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
元信息 = "probe/newpool_1106/panel_meta_newpool.parquet"

# ★★★ 判据来自 1115 本容器实测（★ 不是现编的）—— 出处《195》二节
_基线 = {
    "形状": [3018, 2808],
    "close_sha256_round6": "8868e268cc1277fa",
    "volume_sha256_round6": "b16845d8aaacba8a",
    "close_非空格数": 5615363,
    "跨2016-01-04价比异常只数": 0,          # ★ 接缝那一刀：假接缝那张会是 100 只上下
    "参照票_2015-12-31": {"ABEV": 4.46, "ABT": 44.91, "AEE": 43.23, "AEG": 4.0755, "AEM": 26.28},
    "参照票_2016-01-04": {"ABEV": 4.27, "ABT": 42.93, "AEE": 43.03, "AEG": 3.9965, "AEM": 26.94},
    # ★ panel_meta 的 md5：1115 重烤 == 库里那份（★★ 这一条是**跨容器**查实的）
    "元信息_md5": "c16032d7b1cf2ad5f996fb87a895671b",
}

# ★★ 规矩 76 的池子指纹基线 —— ★★★ 1114 夜 / 1115 **两个容器逐字节相同**那一份
_池基线 = {
    "低": {"成分只数_最少": 824, "调仓次数": 44, "卡玛": 0.208},
    "中": {"成分只数_最少": 607, "成分只数_中位": 914, "调仓次数": 44, "卡玛": 0.181},
    "高": {"成分只数_最少": 338, "调仓次数": 44, "卡玛": 0.172},
}
# ★ 库里 B 路那份（异类）—— ★★ 留在这儿是为了**认出它**，不是为了用它
_池_库里B路 = {"低": 821, "中": 604, "高": 337, "中档卡玛": 0.18}


def _hash(df) -> str:
    import numpy as np
    a = np.nan_to_num(df.to_numpy(dtype="float64"), nan=0.0)
    return hashlib.sha256(np.round(a, 6).tobytes()).hexdigest()[:16]


def 指纹(panel: str = 面板, meta: str = 元信息) -> dict:
    import numpy as np, pandas as pd, pyarrow
    w = pd.read_parquet(panel)
    c = w["close"].astype(float)
    v = w["volume"].astype(float)
    参 = list(_基线["参照票_2015-12-31"])
    r = c.loc["2016-01-04"] / c.loc["2015-12-31"]
    坏 = r[(r > 1.8) | (r < 0.55)]
    出 = {
        "面板": panel,
        "形状": [int(c.shape[0]), int(c.shape[1])],
        "close_sha256_round6": _hash(c),
        "volume_sha256_round6": _hash(v),
        "close_非空格数": int(c.notna().sum().sum()),
        "跨2016-01-04价比异常只数": int(len(坏)),
        "异常最离谱三只": {k: round(float(x), 3)
                          for k, x in 坏.abs().sort_values(ascending=False).head(3).items()},
        "参照票_2015-12-31": {s: round(float(c[s].loc["2015-12-31"]), 4) for s in 参 if s in c.columns},
        "参照票_2016-01-04": {s: round(float(c[s].loc["2016-01-04"]), 4) for s in 参 if s in c.columns},
        "元信息_md5": (hashlib.md5(io.open(meta, "rb").read()).hexdigest()
                      if os.path.exists(meta) else "★ 元信息文件不在"),
        # ★★ 库版本也记下来：1115 之前**没有任何登记点记过它**，跨容器比数时分不清
        #    「输入不同」还是「pandas/numpy 版本不同」（★★★《195》三节）
        "库版本": {"pandas": pd.__version__, "numpy": np.__version__, "pyarrow": pyarrow.__version__},
    }
    不符 = []
    for k in ("形状", "close_sha256_round6", "volume_sha256_round6",
              "close_非空格数", "跨2016-01-04价比异常只数", "元信息_md5"):
        if 出[k] != _基线[k]:
            不符.append(f"{k}: 基线 {_基线[k]} → 现在 {出[k]}")
    for 日 in ("参照票_2015-12-31", "参照票_2016-01-04"):
        for s, 应 in _基线[日].items():
            现 = 出[日].get(s)
            if 现 is None or abs(现 - 应) > 0.002:
                不符.append(f"{日}·{s}: 基线 {应} → 现在 {现}")
    出["★★★对上1115基线了吗"] = not 不符
    出["★不符的项"] = 不符
    出["★判据出处"] = ("1115 本容器实测（《195》二节）· ★★ 元信息 md5 这一条是跨容器查实的"
                      "（1115 重烤 == 库里）· ★★★ 接缝异常只数必须 0")
    return 出


def 必须对上1115基线(panel: str = 面板, meta: str = 元信息) -> dict:
    出 = 指纹(panel, meta)
    if not 出["★★★对上1115基线了吗"]:
        raise AssertionError(
            "★★★★★ newpool 面板与 1115 基线不符 —— **停跑**（规矩 70 / 76 的做法）。\n"
            "★ 不符的项：\n  - " + "\n  - ".join(出["★不符的项"]) +
            "\n★★ 重烤：python3 probe/newpool_1106/烤新池_1106.py（约 51 秒）。\n"
            "★★★ 重烤后仍然不符 → **当场停下来报**，不要接着往下跑（规矩 76）。全文《195》。")
    return 出


def 池指纹(报告: str) -> dict:
    """★★ 规矩 76：池子也要指纹 —— 三档成分只数 + 调仓次数 + 主对标卡玛。"""
    rep = json.load(io.open(报告, encoding="utf-8"))
    三 = rep.get("三点") or {}
    出 = {"报告": 报告, "三点": {}}
    不符 = []
    for 名, 应 in _池基线.items():
        g = 三.get(名) or {}
        现 = {k: g.get(k) for k in 应}
        出["三点"][名] = 现
        for k, a in 应.items():
            if 现.get(k) != a:
                不符.append(f"{名}·{k}: 基线 {a} → 现在 {现.get(k)}")
    出["★★★对上1115基线了吗"] = not 不符
    出["★不符的项"] = 不符
    if 不符:
        低 = (三.get("低") or {}).get("成分只数_最少")
        中 = (三.get("中") or {}).get("成分只数_最少")
        if 低 == _池_库里B路["低"] and 中 == _池_库里B路["中"]:
            出["★★★这是哪一份"] = ("🔴 **库里 B 路那份**（821/604/337 · 中档卡玛 0.18）—— "
                                  "★★ 1114 夜和 1115 两个容器都复现不出它，★★★ 哪份算官方等 Lin 的 DEC-新1")
    else:
        出["★★★这是哪一份"] = "✅ 1114 夜 / 1115 两容器逐字节相同那一份（824/607/338 · 中档卡玛 0.181）"
    return 出


if __name__ == "__main__":
    if "--池" in sys.argv:
        p = sys.argv[sys.argv.index("--池") + 1]
        出 = 池指纹(p)
    else:
        p = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else 面板
        if not os.path.exists(p):
            print(f"★★★ 面板不在：{p}\n★ 先烤：python3 probe/newpool_1106/烤新池_1106.py（约 51 秒）")
            raise SystemExit(2)
        出 = 指纹(p)
    print(json.dumps(出, ensure_ascii=False, indent=1))
    raise SystemExit(0 if 出["★★★对上1115基线了吗"] else 1)
