# -*- coding: utf-8 -*-
"""★★★★★ 查「自述不符」体检 ⑤ 没查的三类（1114 第 1 次唤醒新加）

★★★ 起因：《92》1113 第三轮用体检报的「🔴自述不符 = 0」，把 Lin 清单上
  「25 处自述什么时候改」那一条**划掉了**。★★ 但体检 ⑤ 只查三样：
    (a) common_boundaries.md 头部「共 N 张」 (b)「已内联」自相矛盾 (c)「有 N 小节」
  ★★★★★ 它**不查**下面三类 —— 而这三类正是 11-12 给六张长卡加的「顶部入口块」在用的东西：
    ① 「本卡 N 行」      —— 卡长度自述
    ② 「第 N 行」行号指路 —— ★★★★★ 最危险：文件一长就指到空行/表格分隔线/别的段
    ③ 「八张卡 / N 张卡」 —— 规模自述
  ★★ 判法沿用体检 ④ 的教训：**认结构不认字** ——
     行号对不对，不看数字，看**那条规则自己写出来的关键词**在不在目标行附近 ±窗口 内。

★ 只读不写。退出码 0=没查到红，3=查到红。
"""
import io, os, re, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CARDS = os.path.join(ROOT, "skills_v2")
窗 = 8          # ★ 关键词允许落在目标行 ±8 行内
汉数 = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,
      "十一":11,"十二":12,"十五":15,"十八":18,"二十二":22,"三十八":38,"三十九":39}
空壳 = re.compile(r"^\s*$|^\s*\|[\s\-:|]+\|\s*$|^\s*```|^\s*---+\s*$|^\s*>\s*$")

def 读卡():
    out = {}
    for d in sorted(os.listdir(CARDS)):
        p = os.path.join(CARDS, d, "SKILL.md")
        if os.path.isfile(p):
            out[d] = io.open(p, encoding="utf-8").read()
    return out

def 抽关键词(句):
    """★ 从「第 N 行」所在那一句里，抽出这条规则自己点名的关键词（『』「」或 **粗体**）。"""
    ks = []
    for 正则 in (r"「([^」]{2,24})」", r"『([^』]{2,24})』", r"\*\*([^*]{2,24})\*\*"):
        ks += re.findall(正则, 句)
    ks = [k.strip() for k in ks if not re.fullmatch(r"[★\s\d行第]*", k)]
    # ★ 去掉「第 N 行」自己和纯星号片段
    ks = [k for k in ks if "第" not in k or "行" not in k]
    ks = sorted(set(ks), key=len, reverse=True)
    return ks[:3]

def 读引用():
    """★★★★★ 1114 第 2 次唤醒加：引用层 `references/` `templates/` 里的 *.md。
    ★★ 按**内容**去重 —— ★ 那份 `shared/common_boundaries.md` 在 39 张卡下各有一份副本，
    ★★★ 它们 md5 完全相同，不去重会把同一条错报 39 遍。"""
    import hashlib
    见, out = {}, {}
    for root, _dirs, files in os.walk(CARDS):
        for fn in sorted(files):
            if not fn.endswith(".md") or fn == "SKILL.md":
                continue
            rel = os.path.relpath(os.path.join(root, fn), CARDS)
            txt = io.open(os.path.join(root, fn), encoding="utf-8").read()
            h = hashlib.md5(txt.encode("utf-8")).hexdigest()
            if h in 见:
                out[见[h]]["份数"] += 1
                continue
            见[h] = rel
            out[rel] = {"文": txt, "份数": 1}
    return out


def 查引用层(报, 卡数):
    """★ 同 SKILL.md 那三类口径：① 本文件 N 行 ② 第 N 行指路 ③ N 张卡规模自述。
    ★★★ 指路只在**本文件内部**解析（★ 引用层没有跨卡指行号的写法，1114 实测 0 处）。"""
    引 = 读引用()
    报["★引用层·查了几份"] = f"{len(引)} 份不同内容（★ 磁盘上共 {sum(v['份数'] for v in 引.values())} 个文件，★★ 按 md5 去重）"
    for rel, v in sorted(引.items()):
        txt = v["文"]; 行们 = txt.splitlines(); 真 = len(行们)
        共用 = f"（★ 这一份被 {v['份数']} 张卡引用）" if v["份数"] > 1 else ""
        for m in re.finditer(r"(?:本文件|这一份|这份文件|本份|这个文件)\s*\**\s*"
                             r"(?:刚过|约|大约|共|一共|~|～)?\s*\**\s*(\d{2,4})\s*\**\s*行", txt):
            if int(m.group(1)) != 真:
                报["🔴引用层行数不符"].append(
                    {"文件": rel, "它说": m.group(0), "实际": f"{真} 行", "差": 真 - int(m.group(1)), "★": 共用})
        for m in re.finditer(r"第\s*(?:~|～|约|大约)?\s*(\d{1,4})\s*行", txt):
            n = int(m.group(1))
            行首 = txt.rfind("\n", 0, m.start()) + 1
            行尾 = txt.find("\n", m.end())
            近句 = txt[max(行首, m.start() - 120): min(行尾 if 行尾 > 0 else len(txt), m.end() + 60)]
            记 = {"文件": rel, "它说": f"第 {n} 行", "整句": 近句.strip()[:150], "★": 共用}
            if n > 真:
                记["那份共"] = f"{真} 行"
                报["🔴引用层行号空指"].append(记); continue
            目标行 = 行们[n - 1]
            if 空壳.match(目标行):
                记["那一行现在是"] = 目标行.strip()[:100] or "(空行)"
                报["🔴引用层行号空指"].append(记); continue
            ks = 抽关键词(近句)
            if ks and any(k in 目标行 for k in ks):
                continue
            记["那一行现在是"] = 目标行.strip()[:100]
            报["🟡引用层待人判"].append(记)
        for m in re.finditer(r"([一二三四五六七八九十]{1,3}|\d{1,3})\s*张卡", txt):
            sv = m.group(1)
            n = 汉数.get(sv) or (int(sv) if sv.isdigit() else None)
            # ★★★ 1114b 护栏：「引用它的**每一张卡**」不是规模自述（★ 第一版在引用层误报过一次）
            if re.search(r"(每|任|哪|某|同)\s*$", txt[:m.start()]):
                continue
            if n is None or n == 卡数:
                continue
            近 = txt[max(0, m.start() - 70): m.end() + 70].replace("\n", " ")
            if re.search(r"(更正|原文写|旧数|V1 时期|V1 那|曾经写|原先|从 \d+ 张更新)", 近):
                continue
            if re.search(r"(风险最高|一共|全部|总共|线上|全量|引用它的卡|共用边界)", 近):
                报["🔴引用层规模不符"].append(
                    {"文件": rel, "它说": m.group(0), "实际": f"{卡数} 张", "上下文": 近[:140], "★": 共用})
    return 报


def main():
    卡 = 读卡()
    报 = {"★卡数": len(卡),
         "🔴本卡行数不符": [], "🔴行号空指": [], "🟡行号待人判": [], "✅行号对的": [],
         "🔴规模自述不符": [],
         # ★★★★★ 1114 第 2 次唤醒加的引用层四个格子
         "🔴引用层行数不符": [], "🔴引用层行号空指": [], "🔴引用层规模不符": [], "🟡引用层待人判": [],
         "★★本次没查到的": [
            "★★★★★ 指对了≠那条规则跟正文一致 —— ★ 顶部块「摘到上面的那句话」和正文那一段"
            "**说的是不是同一件事**，本脚本**不查**（★★ 要人读，1114 第 2 轮已逐张读过一遍）。",
            "★★★ 行号指对了≠那条规则本身是对的 —— ★ 本脚本只管指路准不准。",
            "★ 关键词抽不出来的指路（句子里没有「」也没有粗体）→ 记进 🟡，要人看。"]}

    for d, txt in 卡.items():
        行们 = txt.splitlines()
        真行数 = len(行们)

        # ---- ① 「本卡 N 行」
        # ★★★★★ 1114 第 2 次唤醒补：原来只认「本卡 N 行」→ `xing-screener` 写的是
        #   「这张卡 **405 行**」，★★★ 整句从闸下溜过去了（实际 423 行，差 18）。
        for m in re.finditer(
                r"(?:本卡|这张卡|这份卡|本文件|该卡|这一份)\s*\**\s*"
                r"(?:刚过|约|大约|共|一共|~|～)?\s*\**\s*(\d{2,4})\s*\**\s*行", txt):
            说 = int(m.group(1))
            if 说 != 真行数:
                报["🔴本卡行数不符"].append(
                    {"卡": d, "它说": m.group(0), "实际": f"{真行数} 行", "差": 真行数 - 说,
                     "★": "★★★ 这句的用途是「本卡很长、中部走不到」—— ★ 数不对说明写下之后没再核过"})

        # ---- ② 「第 N 行」指路
        # ★★★ 1114 第 2 次唤醒补：「第 **~**371 行」带波浪号/「约」字的也要认 ——
        #   ★ `xing-screener` 第 19 行就是这么写的，原正则不认，★★ 实际指错了 8 行。
        for m in re.finditer(r"第\s*(?:~|～|约|大约)?\s*(\d{1,4})\s*行", txt):
            n = int(m.group(1))
            行首 = txt.rfind("\n", 0, m.start()) + 1
            行尾 = txt.find("\n", m.end())
            整句 = txt[行首: 行尾 if 行尾 > 0 else len(txt)]
            # ★★ 抽关键词只看「第 N 行」前后各 120 字 —— ★ 有的卡一整段写成一行（xing-main 补丁段 700+ 字）
            近句 = txt[max(行首, m.start() - 120): min(行尾 if 行尾 > 0 else len(txt), m.end() + 60)]
            # ★ 指向别的卡？（「screener 第 379 行」「`xing-fundamental-analyst` 第 109 行」）
            目标卡 = None
            前 = txt[max(0, m.start() - 70): m.start()]
            for cand in re.findall(r"[a-z][a-z0-9\-]{3,}", 前):
                for k in 卡:
                    if cand in k and cand != "skill":
                        目标卡 = k
            目标名 = 目标卡 or d
            目标行们 = 卡[目标名].splitlines()
            记 = {"卡": d, "它说": f"第 {n} 行", "指向": 目标名, "整句": 整句.strip()[:150]}
            if n > len(目标行们):
                记.update({"那份共": f"{len(目标行们)} 行",
                         "★": "★★★★★ 行号超出文件长度 —— ★ 照它去翻什么都没有"})
                报["🔴行号空指"].append(记); continue
            目标行 = 目标行们[n - 1]
            ks = 抽关键词(近句)
            低 = max(0, n - 1 - 窗); 高 = min(len(目标行们), n + 窗)
            窗内 = "\n".join(目标行们[低:高])
            真位 = {}
            for k in ks:
                真位[k] = [i + 1 for i, L in enumerate(目标行们) if k in L and i + 1 != n]
            记["找的关键词"] = ks
            记["关键词真在哪几行"] = {k: v[:4] for k, v in 真位.items() if v}
            # ★★★★★ 红 = 机器百分之百确定的那种坏：**指到空行 / 代码围栏 / 表格分隔线 / 水平线**
            if 空壳.match(目标行):
                记.update({"那一行现在是": 目标行.strip()[:100] or "(空行)",
                         "★": "★★★★★ 指到空行/围栏/表格线 —— ★ 照它去翻，那里什么规则都没有"})
                报["🔴行号空指"].append(记); continue
            if ks and any(k in 目标行 for k in ks):
                报["✅行号对的"].append({"卡": d, "它说": f"第 {n} 行", "指向": 目标名}); continue
            记.update({"那一行现在是": 目标行.strip()[:100],
                     "★": ("★★ 关键词不在那一行上 —— ★ 窗口 ±%d 行内%s → **要人判**" % (
                         窗, "有" if any(k in 窗内 for k in ks) else "也没有"))})
            报["🟡行号待人判"].append(记)

        # ---- ③ 规模自述
        for m in re.finditer(r"([一二三四五六七八九十]{1,3}|\d{1,3})\s*张卡", txt):
            s = m.group(1)
            n = 汉数.get(s) or (int(s) if s.isdigit() else None)
            # ★★★ 1114b 护栏：「引用它的**每一张卡**」不是规模自述（★ 第一版在引用层误报过一次）
            if re.search(r"(每|任|哪|某|同)\s*$", txt[:m.start()]):
                continue
            if n is None or n == len(卡):
                continue
            近 = txt[max(0, m.start() - 70): m.end() + 70].replace("\n", " ")
            # ★ 只认说全库规模的；★★ 排除「原文写『八张卡』」这种**正在更正旧数**的引用
            if re.search(r"(更正|原文写|旧数|V1 时期|曾经写)", 近):
                continue
            if re.search(r"(风险最高|一共|全部|总共|线上|全量|引用|共用边界|改本卡等于)", 近):
                报["🔴规模自述不符"].append(
                    {"卡": d, "它说": m.group(0), "实际": f"{len(卡)} 张", "上下文": 近[:140],
                     "★": "★★★ 规模自述过期 —— ★ 这类句子是模型判断「要不要全量检索」的依据"})

    报 = 查引用层(报, len(卡))
    红 = sum(len(v) for k, v in 报.items() if k.startswith("🔴"))
    黄 = sum(len(v) for k, v in 报.items() if k.startswith("🟡"))
    报["★★★三秒版"] = (f"🔴 {红} 条（本卡行数 {len(报['🔴本卡行数不符'])} · 行号空指 "
                   f"{len(报['🔴行号空指'])} · 规模 {len(报['🔴规模自述不符'])}）· "
                   f"🟡 {黄} 条 · ✅ 行号对的 {len(报['✅行号对的'])} 条 · ★ 卡数 {len(卡)}"
                   f" · ★★ 引用层红 {len(报['🔴引用层行数不符']) + len(报['🔴引用层行号空指']) + len(报['🔴引用层规模不符'])} 条"
                   f"（行数 {len(报['🔴引用层行数不符'])} · 行号 {len(报['🔴引用层行号空指'])} · 规模 {len(报['🔴引用层规模不符'])}）"
                   f" · 🟡 {len(报['🟡引用层待人判'])} · ★ 查了 {报['★引用层·查了几份']}")
    tag = os.environ.get("XING_TAG", "1114")
    out = os.path.join(ROOT, "手册", f"查自述_行号与数目_{tag}.json")
    io.open(out, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1))
    print(报["★★★三秒版"])
    for k in ("🔴本卡行数不符", "🔴行号空指", "🔴规模自述不符",
              "🔴引用层行数不符", "🔴引用层行号空指", "🔴引用层规模不符",
              "🟡行号待人判", "🟡引用层待人判"):
        for x in 报[k]:
            print(f"  [{k}] " + json.dumps(x, ensure_ascii=False)[:260])
    print(f"★ 报告：{out}")
    return 3 if 红 else 0
if __name__ == "__main__":
    sys.exit(main())
