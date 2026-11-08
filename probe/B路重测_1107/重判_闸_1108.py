# -*- coding: utf-8 -*-
"""★ 1108:环境闸 28 臂按规矩㊾ 重判 —— 随机闸 100 次的明细都已落盘(A_*.json「随机闸明细」),不用重跑,直接重判。"""
import glob, io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import 台_1107 as T
n = 0
for f in sorted(glob.glob(os.path.join(HERE, "res_22年_1107", "*", "A_*.json"))):
    d = json.load(io.open(f, encoding="utf-8"))
    b = json.load(io.open(os.path.join(os.path.dirname(f), "0_不装.json"), encoding="utf-8"))
    真 = d["装闸"]; 随 = d["随机闸明细"]
    d["★②随机闸对照(100次·分位数·规矩㊾)"] = {
        指: T.噪声判(真[指] - b[指], [x[指] - b[指] for x in 随]) for 指 in ("年化", "最大回撤", "每笔净R")}
    io.open(f, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1, default=str)); n += 1
print("重判", n, "个")
