# -*- coding: utf-8 -*-
"""补《486》第三节缺的 SOXX：直接用主 chat 的 考题重跑_日线版_1127.py 的 跑()，只把 读() 换成能读 SOXX 的（价格用 SC.soxx()，档位用刚补跑的 out4/SOXX_四版_每天的档.csv；2022 年以后不读）。"""
import os, importlib.util, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
K = mod("K", os.path.join(ROOT, "probe/做空开关_1127/考题重跑_日线版_1127.py")); SC = mod("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py"))
def 读(sym):
    D = SC.soxx().loc[:K.封存]; R = pd.read_csv(os.path.join(ROOT, f"probe/大周期五档_1123/out4/{sym}_四版_每天的档.csv"), index_col=0, parse_dates=True).loc[:K.封存]
    return D.loc[D.index.isin(R.index)], R
K.读 = 读
T, 触, 箱 = K.跑("SOXX", 跌幅=0.08)
B = pd.DataFrame(箱); B.to_csv(os.path.join(HERE, "out", "SOXX_筑底箱子.csv"), index=False); pd.set_option("display.width", 250); print(B.to_string(index=False))
A = pd.DataFrame(触); A.to_csv(os.path.join(HERE, "out", "SOXX_转涨触发和撤销.csv"), index=False); print(len(A), "次转涨触发")
