# -*- coding: utf-8 -*-
"""★★★《116》4.1 可复现性闸 —— ★ 跑前写死：不相等就停，这一档的结论一个字都不许发。

★★ 对账范围：突破 / 震荡 两族 × A/B 两段 × (A原样 + 10 条 R随机) = **44 条臂**
   （★ 另 12 条挂闸臂是本档新生成的，旧件里没有，不在对账范围内 —— 《116》3.1 已数清）。
★★★ 比什么：
   ① 日序列：`日序列毛_1107/` 的 `净值`/`敞口` 对 `日序列_1107/` 的同两列 **逐点** abs<=1e-9
      ★ 日期索引也要逐点相等（长度 + 取值）
   ② 臂汇总：`arms_毛_1107/` 对 `arms_1107/` 的 `笔数`（整数相等）与 `每笔净R`（六位小数）
★ engine 零改动；本脚本只读。
"""
import hashlib, json, os, sys
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
R = os.path.join(ROOT, "probe", "重测_1107")
种子 = [424242, 20181001, 20220101, 777013, 31337, 90210, 10007, 31415926, 27182818, 65537]
代表 = {"大波段": "技-1", "突破": "技-6-原著", "震荡": "技-14-原著"}
TOL = 1e-9


def 安全名(label):                       # ★ 照 日序列覆盖层_1107.py:48，不凭记忆
    return hashlib.sha256(label.encode()).hexdigest()[:16]


def 读臂(d, label):
    p = os.path.join(R, d, f"a_{安全名(label)}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


报 = {"★预先登记": "《116》4.1（跑前定稿）", "★容差": {"日序列": "abs<=1e-9", "每笔净R": "六位小数"},
     "逐条": [], "★★★不合格": [], "★跳过(旧件没有)": []}
for 族 in ("突破", "震荡"):
    for 窗 in ("A_2004到2014", "B_2015到2025"):
        for 臂 in ["A原样"] + [f"R随机{s}" for s in 种子]:
            label = f"{窗}·并池2004·{族}·{代表[族]}·{臂}"
            sn = 安全名(label)
            新 = os.path.join(R, "日序列毛_1107", f"d_{sn}.csv")
            旧 = os.path.join(R, "日序列_1107", f"d_{sn}.csv")
            if not os.path.exists(旧):
                报["★跳过(旧件没有)"].append(label); continue
            if not os.path.exists(新):
                报["★★★不合格"].append({"臂": label, "为什么": "本档没生成日序列"}); continue
            a = pd.read_csv(新, parse_dates=["日期"]).set_index("日期")
            b = pd.read_csv(旧, parse_dates=["日期"]).set_index("日期")
            行 = {"臂": label, "点数": int(len(a)), "旧点数": int(len(b))}
            坏 = []
            if len(a) != len(b) or not a.index.equals(b.index):
                坏.append("日期索引不相等")
            else:
                for 列 in ("净值", "敞口"):
                    d = (a[列].astype(float) - b[列].astype(float)).abs().max()
                    行[f"{列}最大绝对差"] = float(d)
                    if not (d <= TOL):
                        坏.append(f"{列}最大差 {d:.3e} > {TOL:.0e}")
            na, nb = 读臂("arms_毛_1107", label), 读臂("arms_1107", label)
            if na and nb:
                行["笔数"] = na["笔数"]; 行["旧笔数"] = nb["笔数"]
                if na["笔数"] != nb["笔数"]:
                    坏.append(f"笔数 {na['笔数']} vs {nb['笔数']}")
                if round(na["每笔净R"], 6) != round(nb["每笔净R"], 6):
                    坏.append(f"每笔净R {na['每笔净R']:.6f} vs {nb['每笔净R']:.6f}")
                行["每笔净R"] = round(na["每笔净R"], 6)
            else:
                行["★臂汇总"] = "旧件缺臂 json，只比了日序列"
            行["判"] = "✅ 相等" if not 坏 else "❌ " + "; ".join(坏)
            if 坏:
                报["★★★不合格"].append({"臂": label, "为什么": 坏})
            报["逐条"].append(行)

报["★★★对账条数"] = len(报["逐条"])
报["★★★结论"] = ("✅ 全部逐点相等 —— 闸通过，可以往下报"
               if not 报["★★★不合格"] else
               "❌❌❌ 有不相等的 —— ★★★ 按《116》4.1 停，结论一个字都不许发")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "对账可复现_报告_1107.json")
json.dump(报, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: 报[k] for k in ("★★★对账条数", "★跳过(旧件没有)", "★★★不合格", "★★★结论")},
                 ensure_ascii=False, indent=1))
sys.exit(0 if not 报["★★★不合格"] else 2)
