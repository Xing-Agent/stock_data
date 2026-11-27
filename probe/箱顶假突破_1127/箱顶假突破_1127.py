# -*- coding: utf-8 -*-
"""《488》第 2 项 · 箱顶假突破全历史（《464 拍板》第 1 条）· 引擎外 · 日线
品种：BTC、ETH（2017 起，不封）、SPY（标普，1993–2021）、SOXX（2001–2021）。美股 2022 年以后不读。
SOXX 先用状态机第四版补跑每天的档（只喂 2021 年以前的数据），参数用 QQQ 那组（P指数 + 箱宽 0.25，我选的；另跑一版 P指数 原样）。

筑底期的箱子：状态机「进筑底期」那天写的箱底、箱顶。
冲出：筑底期里收盘 > 箱顶。
不算有效突破：冲出后最高 ≤ 箱顶 + 0.25×箱高；超过了 = 有效突破（规则判「真」）。
确认假突破：冲出后 窗 天内（20，另试 15、25）收盘 < 箱顶 − 破×ATR（0.3，另试 0.2、0.5），且还没成有效突破 → 规则判「假」，收盘开空。
窗口过了没确认、收盘又回到箱顶下 → 这次冲出作废，重新等下一次冲出（同 486 写法）。
止损：冲出段最高 + 损×ATR（0.5，另试 0.3、0.75）。
目标（拍板）：箱中轴平一半；箱底平 35%（留 15% 尾仓，拍板写 10%~20%，取中）；尾仓到箱底 − 1 倍箱高。
  止损不动（拍板没说移）；最多拿 120 天，到期收盘全走。LPSY（跌破箱底后反抽收不回）没单独判，尾仓直接挂箱底 − 1 倍箱高（我简化的）。
事后真假（我补的，用来数「规则判对几次」）：冲出后 120 天内，先摸到 箱顶 + 1 倍箱高 = 真突破；先收盘跌破箱底 = 假突破；都没有 = 没分出来。另试 0.5 倍箱高。
"""
import os, re, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py"))
SC = mod("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py"))
封 = pd.Timestamp("2021-12-31"); FEE = 0.0005; O4 = os.path.join(ROOT, "probe/大周期五档_1123/out4")


def 价(sym):
    if sym in ("BTC", "ETH"): return M4.币日线(sym)
    if sym == "SOXX": return SC.soxx().loc[:封]
    return M4.美股日线(sym).loc[:封]


def 补SOXX():
    D = 价("SOXX")
    for 名, P in (("SOXX", dict(M4.P指数, 箱宽=0.25)), ("SOXX_指数原参", M4.P指数)):
        R, ev = M4.跑(D, P); R.to_csv(os.path.join(O4 if 名 == "SOXX" else OUT, f"{名}_四版_每天的档.csv"))
        R[R["切换原因"] != ""].to_csv(os.path.join(O4 if 名 == "SOXX" else OUT, f"{名}_四版_切换清单.csv"))
        print(名, R["档"].value_counts().to_dict(), flush=True)


def 档(sym):
    f = os.path.join(O4, f"{sym}_四版_每天的档.csv") if not sym.startswith("SOXX_") else os.path.join(OUT, f"{sym}_四版_每天的档.csv")
    R = pd.read_csv(f, index_col=0, parse_dates=True)
    if sym not in ("BTC", "ETH"): R = R.loc[:封]
    return R


def 跑(sym, 窗=20, 破=0.3, 损=0.5, 真倍=1.0):
    D = 价(sym.split("_")[0]); R = 档(sym); D = D.loc[D.index.isin(R.index)]
    o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(c); idx = D.index
    st = R["档"].reindex(idx).to_numpy(); why = R["切换原因"].reindex(idx).fillna("").to_numpy()
    pc = np.roll(c, 1); pc[0] = c[0]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().bfill().to_numpy()
    box = None; ev = []
    for i in range(1, n):
        m = re.search(r"箱底 ([\d,\.]+)、箱顶 ([\d,\.]+)", why[i])
        if why[i].startswith("进筑底期") and m:
            s0 = max(q for q in range(i) if st[q] == "跌势" and (q == 0 or st[q - 1] != "跌势"))       # 这段跌势的起点
            li = s0 + int(np.argmin(l[s0:i + 1])); 底x = l[li]; 顶x = h[li + 1:i + 1].max() if li < i else h[i]   # 状态机写的箱底箱顶是四舍五入到整数的，这里照它的算法算回原值
            t底, t顶 = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
            if abs(底x - t底) > 0.51 or abs(顶x - t顶) > 0.51: 底x, 顶x = t底, t顶             # 算不回来（低点在这段跌势之前）就用状态机写的数；只有 BTC 2018-04 这一个，数大，取整误差可忽略
            box = dict(起=i, 底=底x, 顶=顶x, 冲=None)
        if box is not None and st[i] != "筑底期" and box["冲"] is None: box = None      # 出了筑底期、又没有挂着的冲出 → 箱子结束
        if box is None: continue
        顶, 底 = box["顶"], box["底"]; 高 = 顶 - 底
        if box["冲"] is None:
            if st[i] == "筑底期" and c[i] > 顶: box.update(冲=i, 段高=h[i], 有效=False)
            continue
        box["段高"] = max(box["段高"], h[i]); k = i - box["冲"]
        if box["段高"] > 顶 + 0.25 * 高 and not box["有效"]: box["有效"] = True; box["有效日"] = i
        判 = None
        if not box["有效"] and k <= 窗 and c[i] < 顶 - 破 * atr[i]: 判 = "假"
        elif box["有效"]: 判 = "真"
        elif k > 窗 and c[i] < 顶: 判 = "作废"
        if 判 is None: continue
        j = box["冲"]; e = dict(品种=sym, 箱起=str(idx[box["起"]].date()), 箱底=底, 箱顶=顶, 箱高pct=高 / 顶 * 100, 冲出日=str(idx[j].date()), 规则判=判, 判的日子=str(idx[i].date()), 冲出段最高=box["段高"])
        # 事后真假
        tg = 顶 + 真倍 * 高; 后 = None
        for q in range(j + 1, min(j + 121, n)):
            if h[q] >= tg: 后 = "真"; break
            if c[q] < 底: 后 = "假"; break
        e["事后"] = 后 or "没分出"
        if 判 == "假":
            E = c[i]; S = box["段高"] + 损 * atr[i]; Rk = S - E; 中 = (顶 + 底) / 2; 尾 = 底 - 高
            parts = [(0.5, 中), (0.35, 底), (0.15, 尾)]; 剩 = {p: True for p in range(3)}; pnl = 0.0; 到 = []
            end = min(i + 120, n - 1); 出 = None
            for q in range(i + 1, end + 1):
                if h[q] >= S:
                    px = max(S, o[q]) if not np.isnan(o[q]) else S
                    pnl += sum(parts[p][0] * (E - px) for p in range(3) if 剩[p]); 出 = q; break
                for p in range(3):
                    if 剩[p] and l[q] <= parts[p][1]: pnl += parts[p][0] * (E - parts[p][1]); 剩[p] = False; 到.append(p)
                if not any(剩.values()): 出 = q; break
            if 出 is None: pnl += sum(parts[p][0] * (E - c[end]) for p in range(3) if 剩[p]); 出 = end
            pnl -= 2 * FEE * E
            e.update(进场=E, 止损=S, 风险pct=Rk / E * 100, 收益pct=pnl / E * 100, R=pnl / Rk, 到中轴=0 in 到, 到箱底=1 in 到, 到尾仓目标=2 in 到, 拿了几天=出 - i)
        ev.append(e)
        if 判 in ("假", "作废"): box["冲"] = None                                     # 重新等下一次冲出
        else: box = None                                                             # 真突破：这个箱子结束
    return ev


if __name__ == "__main__":
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400)
    if not os.path.exists(os.path.join(O4, "SOXX_四版_每天的档.csv")) or "--补" in sys.argv: 补SOXX()
    rows = []
    for s in ("BTC", "ETH", "SPY", "SOXX", "SOXX_指数原参"):
        for 窗 in (15, 20, 25):
            for kw_n, kw in (("默认", {}), ("破0.2", {"破": 0.2}), ("破0.5", {"破": 0.5}), ("损0.3", {"损": 0.3}), ("损0.75", {"损": 0.75}), ("事后0.5倍", {"真倍": 0.5})):
                if 窗 != 20 and kw_n != "默认": continue
                rows += [dict(r, 窗=窗, 参数=kw_n) for r in 跑(s, 窗, **kw)]
    T = pd.DataFrame(rows); T.to_csv(os.path.join(OUT, "冲出逐次.csv"), index=False)
    print(T[(T.窗 == 20) & (T.参数 == "默认")].drop(columns=["窗", "参数"]).round(2).to_string(index=False))
    print("DONE")
