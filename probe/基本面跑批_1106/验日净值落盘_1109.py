# -*- coding: utf-8 -*-
"""★★★★★ Lin 1109 拍板第 4 条的第二步 —— ★ **先跑 1 条、眼睛看到 csv 落地**，再放整批。

★★ 为什么要单独一份：规矩 51 / 账本 #83 —— 「预先登记里写了拿什么做检验，
  跑之前必须确认它真的会落盘」。★★★ 1108 两次栽的都是「自证打出来好看、东西没真生效」
  （#101 分红折算没执行 ·《131》逃生门写成中文变量名根本打不开）。
★ 所以这一份**不信打印出来的那行**，而是**把 csv 读回来**再查五件（见 查曲线）。

★★★ 它**不是跑批**，产出也**不是结果**：
  · 随机对照只跑 2 次（整批是 100 次）→ ★★ 所以本脚本**不写臂 JSON**，
    免得出现一个「标签写 100 次、其实 2 次」的文件（★★★ 标签说谎那一类，#80/#96）。
  · 只验一件事：真链那一次的 `res.equity / equity_gross / exposure` 有没有**真的落盘、读得回来**。

★ 用法（★★ 三个目录一起换，别碰库里那 33 条）：
    XING_ARMS_DIR=arms_验落盘_1109 XING_LEDG_DIR=ledgers_验落盘_1109 \
      XING_NAV_DIR=日净值_验落盘_1109 \
      python3 probe/基本面跑批_1106/验日净值落盘_1109.py ["臂名"]
★★ 退出码：0 = 五件全过 · 1 = 有一件没过（★ 那就**不许放整批**）。
"""
from __future__ import annotations
import io, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

if not os.environ.get("XING_NAV_DIR"):
    raise SystemExit("★★★★★ 停 —— 必须显式给 XING_NAV_DIR（不给就不落盘，验不了）。见本文件用法。")
if os.environ.get("XING_ARMS_DIR") in (None, "arms_2009修接缝"):
    raise SystemExit("★★★★★ 停 —— XING_ARMS_DIR 必须换成验证专用目录，"
                     "★ 不然会盖掉库里入库的那 33 条臂。见本文件用法。")

import 跑基本面_1106 as R0                                       # noqa: E402
import 跑基本面_2009 as R2                                       # noqa: E402

臂名 = sys.argv[1] if len(sys.argv) > 1 else R0.臂表()[0]["臂"]
arm = next(a for a in R0.臂表() if a["臂"] == 臂名)

# ★★★ 随机对照从 100 降到 2 —— ★ 本脚本只验落盘，★★ 而且因此**不写臂 JSON**（见文件头）。
R2.N随机 = 2
print(f"★★★ 验落盘开始 · 臂 = {臂名}", flush=True)
print(f"★ 面板 = {R2.PANEL}", flush=True)
print(f"★★ 曲线目录 = {os.environ['XING_NAV_DIR']} · 臂目录 = {os.environ['XING_ARMS_DIR']}"
      f"（★ 本脚本不写臂 JSON）", flush=True)

# ★★ 跑前先把面板身份验一道（规矩 70）—— ★★★ 跑错面板不如不跑
# ★★★★★ 1109 实测：这一道**必须开子进程**，不许在本进程里 import ——
#   ★ 在本进程里跑，`指纹()` 读进来的那张 close 矩阵（5747×3858）**不会被及时还给系统**，
#     ★★ 接着 `matrices.build` 一上来就 OOM（7 GB 机器，实测 **Killed**，第一次就撞上）。
#   ★★★ 这正是「跑前自检本身把跑批挤死」这一类 —— ★ 自检要便宜，不能占着内存不放。
import subprocess                                                # noqa: E402
_r = subprocess.run([sys.executable, "probe/审计复核_1108/面板指纹_1108.py", R2.PANEL],
                    cwd=ROOT, capture_output=True, text=True)
if _r.returncode != 0:
    print(_r.stdout[-2000:])
    raise SystemExit("★★★★★ 停 —— 面板指纹不是修接缝版（规矩 70）。★ 跑错面板不如不跑。")
指纹 = json.loads(_r.stdout)
print(f"★★★ 面板指纹过了（子进程）：形状 {指纹['形状']} · "
      f"异常 {指纹['跨2016-01-04价比异常只数']} 只 · "
      f"AAPL {指纹['AAPL_2015-12-31']}/{指纹['AAPL_2016-01-04']}", flush=True)

t0 = time.time()
rec = R2.跑一条(arm)
用时 = time.time() - t0
print(f"★ 跑完 {用时:.0f} 秒（★★ 其中建矩阵 {rec.get('建矩阵秒')} 秒）", flush=True)
print(f"★★★ 臂记录里的日净值字段：{rec.get('★★★日净值')}", flush=True)


def 查曲线(路径: str, 窗口交易日: int) -> dict:
    """★★★ 不信打印的那行 —— ★ 把 csv 读回来查五件。"""
    import pandas as pd
    出, 过 = {}, []
    d = pd.read_csv(路径, parse_dates=["date"]).set_index("date")
    出["①列名对不对"] = list(d.columns)
    过.append(list(d.columns) == ["equity", "equity_gross", "exposure"])
    出["②天数"] = f"{len(d)} 天（★ 绩效窗口 {窗口交易日} 天）"
    过.append(abs(len(d) - 窗口交易日) <= 2)
    出["③日期递增且无重复"] = bool(d.index.is_monotonic_increasing and d.index.is_unique)
    过.append(出["③日期递增且无重复"])
    eq = d["equity"].astype(float)
    出["④equity 首→尾"] = f"{eq.iloc[0]:.4f} → {eq.iloc[-1]:.4f}"
    过.append(bool(eq.notna().all() and (eq > 0).all() and abs(eq.iloc[0] - 1.0) < 0.05))
    出["⑤能不能算出日收益率"] = f"{int(eq.pct_change().dropna().shape[0])} 个"
    过.append(eq.pct_change().dropna().shape[0] >= 30)
    出["★★★五件全过吗"] = all(过)
    出["★逐件"] = 过
    return 出


曲线 = os.path.join(HERE, os.environ["XING_NAV_DIR"],
                   f"{R0.安全名(臂名)}.csv")
if not os.path.exists(曲线):
    print(f"★★★★★ 没过 —— 曲线文件不在：{曲线}")
    raise SystemExit(1)
报 = {"★这是什么": "Lin 1109 拍板④ 第二步：基本面跑批器落盘日净值的落地自证（★ 不是结果）",
     "臂": 臂名, "面板指纹": 指纹, "用时秒": round(用时, 1),
     "建矩阵秒": rec.get("建矩阵秒"), "曲线文件": os.path.relpath(曲线, ROOT),
     "★★★读回来查五件": 查曲线(曲线, int(rec.get("绩效窗口交易日") or 0)),
     "★随机对照": "本脚本只跑 2 次（整批是 100 次）→ ★★ 所以不写臂 JSON，不出成绩",
     "★★下一步": "五件全过 → 才按《102》那样写跑前预先登记，再放 33 条整批（4~7 小时）"}
io.open(os.path.join(HERE, "验日净值落盘_报告_1109.json"), "w", encoding="utf-8").write(
    json.dumps(报, ensure_ascii=False, indent=1, default=str))
print(json.dumps(报["★★★读回来查五件"], ensure_ascii=False, indent=1), flush=True)
过 = 报["★★★读回来查五件"]["★★★五件全过吗"]
print(("✓✓ 五件全过 —— ★ 落盘这一步成立" if 过 else "★★★★★ 没过 —— 不许放整批"), flush=True)
raise SystemExit(0 if 过 else 1)
