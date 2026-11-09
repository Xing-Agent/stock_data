# -*- coding: utf-8 -*-
"""★★★ 规矩 60（#90）落地 —— ★ 容器初始化清单**不手写**，从跑批实际读的路径反推。

★★ 用法：`python3 probe/重测_1107/跑前查派生物_1107.py`
   → 缺什么就**大声报**并给出重建命令（规矩⑯ 响亮失败），全齐返回 0，缺一个返回 2。
★★★ 为什么要有它：《92》零节那份手写清单在池子从「新池 2,224」换到「并池 3,858」之后
   就过期了 —— ★ 照它做完两件起跑批，跑到装池那一步才 FileNotFoundError，白烧 560 秒。
★ 这份清单里的每一条路径都是**从跑批代码里 grep 出来的**，不是凭记忆写的。
"""
import importlib.util, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

要的 = [
    # ★★★★★ 1109 第 5 次唤醒改掉的：原来这两行写的重建命令是
    #   `probe/并池_1107/烤并池_1107.py` —— ★★★ 那一份烤出来的是**假接缝那张**
    #   （跨 2016-01-04 异常 100 只 · AAPL 105.26/26.34），★ 已按 Lin 1109 拍板第 3 条作废。
    #   ★★ 新容器里照它重建，会把**被作废的面板**放到「应该放修接缝版」的那个路径上；
    #   ★★★ 只有串跑侧的规矩 70 指纹闸挡着它 → ★ 这里直接改成对的那一份（《126》3.1 / 面板来源_1108.txt）。
    ("probe/并池2004_1107/ohlcv_panel_newpool.parquet",
     "python3 probe/基本面跑批_1106/烤并池2004修接缝_A路_1108.py"
     " && cp probe/基本面跑批_1106/并池2004修接缝_1108/*.parquet probe/并池2004_1107/",
     "约 165 秒 · 并池2004 全量 3,858 只 —— ★★★ 必须是**修接缝版**"),
    ("probe/并池2004_1107/panel_meta_newpool.parquet",
     "python3 probe/基本面跑批_1106/烤并池2004修接缝_A路_1108.py"
     " && cp probe/基本面跑批_1106/并池2004修接缝_1108/*.parquet probe/并池2004_1107/",
     "★ 第五个登记点（规矩 52）"),
    ("probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv",
     "★ 入库文件，不用重建", "池表（第三个登记点）"),
]
# ★★★ 老池那条线（friction_rerun_1104 那 44 条臂）另外要一份 `engine/cache/ohlcv_panel.parquet`。
#   ★★ 核过（不凭记忆、不信台账）：
#     · `engine/cache.py:159` —— `load()` 自己判断「不存在就 build()」→ ★ **它会自己烤，不用手动跑**
#     · `烤新池_1106.py:182` 只写 `probe/newpool_1106/ohlcv_panel_newpool.parquet`
#       → ★★★ 所以《92》零节那句「engine/cache/ohlcv_panel.parquet 跑烤新池时顺带生成」**是错的**，
#         ★ 不过无害（cache.load() 会补），所以这里只标成「选配」，不计入缺项。
老池面板 = "engine/cache/ohlcv_panel.parquet"
包 = [("pyarrow", "pip install pyarrow --break-system-packages"),
     ("statsmodels", "pip install statsmodels --break-system-packages"),
     ("yaml", "pip install pyyaml --break-system-packages")]

缺 = []
print("★★★ 跑前查派生物（规矩 60）")
for p, cmd, 说 in 要的:
    有 = os.path.exists(os.path.join(ROOT, p))
    大小 = (f"{os.path.getsize(os.path.join(ROOT, p)) / 1e6:.0f} MB" if 有 else "—")
    print(f"  {'✅' if 有 else '❌'} {p}  [{大小}]  {说}")
    if not 有:
        缺.append(f"★ 缺 {p} → 重建：{cmd}")
print(f"  {'✅' if os.path.exists(os.path.join(ROOT, 老池面板)) else '○'} {老池面板}"
      f"  [选配 · 只有老池那 44 条臂要它；缺了 engine/cache.py:159 的 load() 会自己烤，"
      f"也可以 `python3 -m engine.cache --rebuild`]")
for m, cmd in 包:
    有 = importlib.util.find_spec(m) is not None
    print(f"  {'✅' if 有 else '❌'} python 包 {m}")
    if not 有:
        缺.append(f"★ 缺 python 包 {m} → {cmd}")

# ★★★★★ 1109 第 5 次唤醒加的第四件：**面板在不在**不等于**面板对不对**。
#   ★★★ 规矩 70 的指纹闸原来只装在 `串跑_1107.sh:71`；★ 这份「跑前查」会对一张
#   被作废的假接缝面板打 ✅ —— ★★ 按规矩⑯「响亮失败」，这一条要在**跑前**就响。
if os.path.exists(os.path.join(ROOT, 要的[0][0])):
    try:
        import pandas as _pd
        _cl = _pd.read_parquet(os.path.join(ROOT, 要的[0][0]), columns=None)["close"]
        _r = _cl.loc["2015-12-31"], _cl.loc["2016-01-04"]
        _比 = (_r[1] / _r[0]).dropna()
        _异常 = int(((_比 > 1.8) | (_比 < 0.55)).sum())
        _aapl = (round(float(_cl["AAPL"].loc["2015-12-31"]), 2),
                 round(float(_cl["AAPL"].loc["2016-01-04"]), 2))
        _修 = (_异常 == 0 and _aapl == (26.32, 26.34))
        print(f"  {'✅' if _修 else '🔴'} 面板身份（规矩 70）：跨 2016-01-04 异常 {_异常} 只 · "
              f"AAPL {_aapl[0]}/{_aapl[1]} → {'修接缝版' if _修 else '★★★★★ 假接缝版，已作废'}")
        if not _修:
            缺.append("★★★★★ 面板是**假接缝版**（已按 Lin 1109 拍板第 3 条作废）→ "
                     "删掉 probe/并池2004_1107/*.parquet，按上面那条重建命令重烤")
        del _cl
    except Exception as _e:                                     # noqa: BLE001
        print(f"  🔴 面板身份查不了：{str(_e)[:90]}")
        缺.append("★★★ 面板身份（规矩 70）查不了 → 先把它查通再起跑批，不许跳过")

if 缺:
    print("\n★★★★★ 不齐 —— 跑批**先别起**（规矩⑯：响亮失败，不要跑到一半才抛）：")
    for s in 缺:
        print("   " + s)
    sys.exit(2)
print("\n✅ 全齐 —— 可以起跑批（★★ 规矩⑩：先 `ps -eo args | grep 跑重测` 确认没有另一份在跑）")
