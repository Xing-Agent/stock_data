# -*- coding: utf-8 -*-
"""★ 把 res_22年_1107/ 和 环境卡结果_22年_1107.json 汇成报告用的表(打印 markdown + 写 汇总_22年_1107.json)。
★★ 规矩⑯:哪个文件缺了 / 跑失败了,大声报,不许打空表。"""
import glob, io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "res_22年_1107")
宿主 = ["技-1·大波段", "技-6-原著·突破", "技-14-原著·震荡", "技-12·震荡"]
闸 = ["均线100·波动20·中位252", "均线200·波动20·中位252", "均线300·波动20·中位252",
     "均线200·波动10·中位252", "均线200·波动40·中位252", "均线200·波动20·中位126", "均线200·波动20·中位504"]
缺, 失败, 行 = [], [], {"闸": [], "挂件": [], "宿主": []}


def rd(p):
    if not os.path.exists(p):
        缺.append(os.path.relpath(p, HERE)); return None
    return json.load(io.open(p, encoding="utf-8"))


for h in 宿主:
    d = os.path.join(RES, h)
    for f in glob.glob(os.path.join(d, "*失败*.json")):
        失败.append(os.path.relpath(f, HERE))
    b = rd(os.path.join(d, "0_不装.json")); c = rd(os.path.join(d, "C_排序噪声.json"))
    if b:
        行["宿主"].append({"宿主": h, "笔数": b["笔数"], "每笔净R": b["每笔净R"], "年化": b["年化"], "最大回撤": b["最大回撤"],
                       "平均仓位": b["平均仓位"], "基准": b["基准"],
                       "排序噪声sd": c and c["★单次噪声一个标准差(每笔净R)"], "生产排序距随机": c and c["生产排序距随机几个标准差"]})
    for g in 闸:
        a = rd(os.path.join(d, f"A_{g}.json"))
        if not a:
            continue
        pr = a["★①配对检验(日收益逐日相减)"]; z = a.get("★②随机闸对照(100次·分位数·规矩㊾)") or a["★②随机闸对照(100次·标准差)"]
        行["闸"].append({"宿主": h, "门槛": g, "关闸天数": a["自证"]["关闸天数(窗口内)"],
                       "装闸年化": a["装闸"]["年化"], "装闸回撤": a["装闸"]["最大回撤"],
                       "年化差": z["年化"].get("真"), "年化差_随机均值": z["年化"].get("随机均值"), "年化差_随机sd": z["年化"].get("随机标准差"),
                       "年化差_z": z["年化"].get("距随机几个标准差"), "年化差_判": z["年化"]["★判"],
                       "年化差_随机95%": z["年化"].get("★★★随机95%范围_分位数"), "年化差_p右": z["年化"].get("★★★经验p_右尾"), "年化差_偏度": z["年化"].get("★★★偏度"), "年化差_打架": "★★★★★两种判法打架" in z["年化"],
                       "回撤差_随机95%": z["最大回撤"].get("★★★随机95%范围_分位数"), "回撤差_打架": "★★★★★两种判法打架" in z["最大回撤"],
                       "回撤差": z["最大回撤"].get("真"), "回撤差_z": z["最大回撤"].get("距随机几个标准差"), "回撤差_判": z["最大回撤"]["★判"],
                       "配对_日均差年化pct": pr["日均差_年化pct"], "配对_t": pr["t(按月聚类)"], "配对_判": pr["★判"]})
    for f in sorted(glob.glob(os.path.join(d, "B_*.json"))):
        if "失败" in f:
            continue
        x = json.load(io.open(f, encoding="utf-8")); t = x["★①配对检验(同进场逐笔)"]
        k = "★②随机砍单对照(1000次·分位数·规矩㊾)" if "★②随机砍单对照(1000次·分位数·规矩㊾)" in x else [y for y in x if y.startswith("★②")][0]; j = x[k]
        行["挂件"].append({"宿主": h, "挂件": os.path.basename(f)[2:-5], "砍掉": t["砍掉笔数"], "共同": t["共同"],
                        "收益差pct": t["收益差pct"], "t": t["收益差t"], "配对判": t["收益差判"],
                        "随机均值": j["收益差pct"].get("随机均值"), "随机sd": j["收益差pct"].get("随机标准差"),
                        "z": j["收益差pct"].get("距随机几个标准差"), "随机判": j["收益差pct"]["★判"], "随机95%": j["收益差pct"].get("★★★随机95%范围_分位数"), "偏度": j["收益差pct"].get("★★★偏度"), "打架": "★★★★★两种判法打架" in j["收益差pct"], "已重判": "分位数" in k,
                        "误杀率": t["误杀率"], "在场比": t["在场比"]})
卡 = rd(os.path.join(HERE, "环境卡结果_22年_1107.json"))
行["卡"] = []
if 卡:
    for h in 宿主:
        for k, v in (卡.get(h) or {}).items():
            if not isinstance(v, dict) or "减半笔数" not in v:
                continue
            e = v.get("调仓位效果·比大盘pct") or {}; pr = v.get("①配对检验·差档减其余·比大盘") or {}
            行["卡"].append({"宿主": h, "卡": k, "减半占比": v.get("减半占比"), "判": v.get("★判") or e.get("★判"),
                           "效果pct": e.get("真"), "随机均值": e.get("随机均值"), "随机sd": e.get("随机标准差"), "z": e.get("距随机几个标准差"), "随机95%": e.get("★★★随机95%范围_分位数"), "偏度": e.get("★★★偏度"), "打架": "★★★★★两种判法打架" in e,
                           "差档减其余pct": v.get("差档减其余·比大盘pct"), "配对t": pr.get("t"), "配对判": pr.get("★判定")})
    失败 += 卡.get("★★★失败", [])
out = {"★★★缺的文件": 缺, "★★★跑失败": 失败, **行}
io.open(os.path.join(HERE, "汇总_22年_1107.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print("缺", len(缺), 缺[:10]); print("失败", len(失败), 失败[:5])
for k in ("宿主", "闸", "挂件", "卡"):
    print(f"== {k}: {len(行[k])} 行")
