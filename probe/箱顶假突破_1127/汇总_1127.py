import os, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); pd.set_option("display.width", 250)
T = pd.read_csv(os.path.join(OUT, "冲出逐次.csv")); R = {}
def 汇(x):
    y = x[x["规则判"] == "假"]; 分 = x[x["事后"] != "没分出"]; 对 = 分[分["规则判"].isin(["真", "假"])]
    return pd.Series({"冲出": len(x), "规则判假": int((x.规则判 == "假").sum()), "规则判真": int((x.规则判 == "真").sum()), "作废": int((x.规则判 == "作废").sum()),
                      "事后真": int((x.事后 == "真").sum()), "事后假": int((x.事后 == "假").sum()), "没分出": int((x.事后 == "没分出").sum()),
                      "判对/能对的": f"{int((对.规则判 == 对.事后).sum())}/{len(对)}", "空笔数": len(y), "每笔%": round(y.收益pct.mean(), 1) if len(y) else None, "每笔R": round(y.R.mean(), 2) if len(y) else None,
                      "赚钱": f"{int((y.收益pct > 0).sum())}/{len(y)}", "最深%": round(y.收益pct.min(), 1) if len(y) else None})
for key in (["窗", "品种"], ["参数", "品种"]):
    sub = T if key[0] == "窗" else T[T.窗 == 20]
    if key[0] == "窗": sub = sub[sub.参数 == "默认"]
    A = sub.groupby(key).apply(汇).reset_index(); print(A.to_string(index=False)); R["按" + key[0]] = A.to_dict("records")
json.dump(R, open(os.path.join(OUT, "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
