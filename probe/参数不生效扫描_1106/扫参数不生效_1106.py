# -*- coding: utf-8 -*-
"""
★★★ 全库扫「参数写在 params 还是顶层」的不一致 —— 这类 bug **不报错,只给错数**。

★ 起因:1106 查出 `engine/matrices.py:604` 的 index_above_ma 从**规则顶层**取
  `rule.get("ma", 200)`,而兄弟分支 index_above_ma_scaled(:632)先做
  `p = rule.get("params", rule)`。★★ 我们把 ma 写在 params 里 → **被静默忽略,退回默认值**。
★★★ 这一次是靠「三档数字完全相同」才发现的 —— ★ 如果当初扫的是 100/300/400,
  三档也会完全相同,而我可能会写成「参数不敏感」,**一个凭空的结论**。

★★ 做法(两头对):
  ① **代码侧**:在 matrices.py 里找出所有 `if t == "..."` 分支,
     看它**读参数之前有没有先做** `rule.get("params", rule)`。没做的 = 只认顶层。
  ② **配置侧**:扫全部 yaml,看每条规则的参数**实际写在哪一层**。
  ③ 两边一比:**「代码只认顶层」而「配置写在 params」= 静默失效。**

★★★ 只读,不改 engine 一个字节。
"""
from __future__ import annotations
import glob, io, json, os, re
import yaml

ROOT = os.path.abspath(".")
OUT = "probe/参数不生效扫描_1106"
SRC = ["engine/matrices.py", "engine/ops_exits_1029.py", "engine/pat6_ops.py"]


def 扫代码() -> dict:
    """★ 返回 {类型名: '只认顶层' / '认 params' / '看不出'}。
    ★★ 判法:从该分支起到下一个分支之前的代码块里,
       有 `rule.get("params"` 或 `p = ` 之类 → 认 params;
       直接出现 `rule.get("` 或 `rule["` 取业务参数 → 只认顶层。"""
    out, 证据 = {}, {}
    for f in SRC:
        if not os.path.exists(f):
            continue
        src = io.open(f, encoding="utf-8").read().splitlines()
        # 找所有分支起点
        starts = []
        for i, ln in enumerate(src):
            m = re.search(r'^\s*(?:el)?if t == "([a-z_0-9]+)"', ln)
            if m:
                starts.append((i, m.group(1)))
            m2 = re.search(r'^\s*(?:el)?if t in \(([^)]*)\)', ln)
            if m2:
                for q in re.findall(r'"([a-z_0-9]+)"', m2.group(1)):
                    starts.append((i, q))
        for k, (i, t) in enumerate(starts):
            j = starts[k + 1][0] if k + 1 < len(starts) else min(i + 40, len(src))
            blk = "\n".join(src[i:j])
            认params = bool(re.search(r'rule\.get\(\s*["\']params["\']', blk)) or \
                        bool(re.search(r'\bp\s*=\s*rule', blk))
            # ★ 取业务参数时直接读 rule 顶层(排除 type/source/params 本身)
            顶层读 = [x for x in re.findall(r'rule(?:\.get\(|\[)\s*["\']([a-z_0-9]+)["\']', blk)
                      if x not in ("type", "source", "params")]
            if 认params:
                v = "认 params"
            elif 顶层读:
                v = "★★★ 只认顶层"
            else:
                v = "看不出(该分支没读参数)"
            # 同名多处:以「只认顶层」为准(最坏情况)
            if out.get(t) != "★★★ 只认顶层":
                out[t] = v
                证据[t] = {"文件": f, "行": i + 1, "顶层读到的键": sorted(set(顶层读))}
    return {"判定": out, "证据": 证据}


def 扫配置() -> list:
    rows = []
    for f in sorted(glob.glob("engine/configs/*.yaml")) + \
             sorted(glob.glob("probe/*/configs/*.yaml")):
        try:
            d = yaml.safe_load(io.open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for 槽 in ("universe", "regime", "entry", "exit"):
            for idx, r in enumerate((d.get(槽) or {}).get("rules") or []):
                if not isinstance(r, dict):
                    continue
                顶层 = sorted(k for k in r if k not in ("type", "source", "params"))
                inp = sorted((r.get("params") or {}).keys())
                rows.append({"文件": os.path.relpath(f, ROOT), "槽": 槽, "序": idx,
                             "类型": r.get("type"), "顶层键": 顶层, "params键": inp})
    return rows


def main() -> int:
    代码 = 扫代码()
    配置 = 扫配置()
    判定 = 代码["判定"]
    风险, 安全, 未知 = [], 0, []
    for c in 配置:
        t, v = c["类型"], 判定.get(c["类型"])
        if v is None:
            未知.append(c); continue
        if v == "★★★ 只认顶层" and c["params键"] and not c["顶层键"]:
            风险.append({**c, "★问题": "代码只认顶层,配置写在 params → **静默失效,退回默认值**",
                        "证据": 代码["证据"].get(t)})
        elif v == "★★★ 只认顶层" and c["params键"] and c["顶层键"]:
            风险.append({**c, "★问题": "代码只认顶层,配置两层都有 → params 里那部分失效",
                        "证据": 代码["证据"].get(t)})
        else:
            安全 += 1
    os.makedirs(OUT, exist_ok=True)
    rep = {"★这是什么": "扫「代码只认顶层 + 配置写在 params」= 静默失效的组合",
           "★为什么要扫": "这类 bug 不报错,只给错数;1106 靠「三档数字完全相同」才发现一处",
           "扫的代码文件": SRC, "规则实例总数": len(配置),
           "★★★ 有风险的": len(风险), "安全的": 安全, "类型判不出的": len(未知),
           "代码侧判定": 判定, "风险明细": 风险,
           "类型判不出的明细": 未知[:20]}
    io.open(os.path.join(OUT, "扫描结果_1106.json"), "w", encoding="utf-8").write(
        json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"★ 规则实例 {len(配置)} 条 · ★★★ 有风险 {len(风险)} 条 · 安全 {安全} · 判不出 {len(未知)}\n")
    if 风险:
        print("★★★ 有风险的（代码只认顶层，而配置写在 params）：")
        seen = set()
        for r in 风险:
            key = (r["类型"], r["文件"])
            if key in seen: continue
            seen.add(key)
            e = r.get("证据") or {}
            print(f"   {r['类型']:28s} {r['文件']:46s} params={r['params键']}")
            print(f"      → 代码 {e.get('文件')}:{e.get('行')} 顶层读 {e.get('顶层读到的键')}")
    print("\n★ 代码侧「只认顶层」的类型：")
    print("   " + " · ".join(sorted(t for t, v in 判定.items() if v == "★★★ 只认顶层")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
