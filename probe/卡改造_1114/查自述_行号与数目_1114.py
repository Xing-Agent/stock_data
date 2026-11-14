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

def 去饰(s):
    """★★★ 1114 第 5 次唤醒加：去掉 markdown 强调和装饰符再比。
    ★★ 为什么这不算放宽：比的还是**同一句话**，★★★ 只是不再因为
       「封存段**任何界面都不许泄露**」里那两个星号的位置不同就判成不符。
    ★ 1114-4 逐条核过的 8 张黄里，有 2 张纯粹坏在这件上。"""
    return re.sub(r"[*★#>│｜\s`.、,，]", "", s)


def 是标题行(行):
    """★ 只认 markdown 标题（`#`~`######`）—— ★★★ 不认「粗体当标题」那种写法，宁可留黄。"""
    return bool(re.match(r"\s*#{1,6}\s", 行))


def 抽小节名(句, m):
    """★★★★★ 1114 第 5 次唤醒加：自述写「第 N 行 · §4 风险字段」时，拿**小节名**去比标题。

    ★★ 口径（★★★ 刻意写窄，宁可留黄不要误绿）：
      · 只看「第 N 行」**后面**那一小段，到第一个 `）` `)` 或换行为止；
      · 这一段里有 `§` → 小节名 = `§` 后面那串；
      · 没有 `§` 但以 `·` 引出 → 小节名 = 第一个 `·` 后面那串；
      · 其它写法（「第 79 行有理由」「那一节在 … 第 379 行」）→ **不给名字，照旧留黄**。
    """
    i = 句.find(m.group(0))
    if i < 0:
        return ""
    尾 = 句[i + len(m.group(0)):]
    尾 = re.split(r"[）)\n]", 尾, maxsplit=1)[0]
    g = re.search(r"§\s*(.+)$", 尾)
    if g:
        return g.group(1).strip()
    g = re.search(r"^[\s★]*·\s*(.+)$", 尾)
    if g:
        return g.group(1).strip()
    return ""


def 抽关键词(句):
    """★ 从「第 N 行」所在那一句里，抽出这条规则自己点名的关键词（『』「」或 **粗体**）。"""
    ks = []
    for 正则 in (r"「([^」]{2,24})」", r"『([^』]{2,24})』", r"\*\*([^*]{2,24})\*\*"):
        ks += re.findall(正则, 句)
    ks = [k.strip() for k in ks if not re.fullmatch(r"[★\s\d行第]*", k)]
    # ★ 去掉「第 N 行」自己和纯星号片段
    ks = [k for k in ks if "第" not in k or "行" not in k]
    # ★★★ 1114-5 补：引号**跨行没闭合**那种 —— ★ piotroski 第 94 行就是
    #   「**缺一项就标 UNKNOWN，<换行>输出『…』**」，★★ 原正则要求闭合 → 这条关键词根本没抽出来。
    g = re.search(r"[「『]\s*\**([^」』*\n]{4,40}?)\s*$", 句)
    if g:
        ks.append(g.group(1).strip())
    ks = [k.strip() for k in ks if not re.fullmatch(r"[★\s\d行第]*", k)]
    ks = [k for k in ks if "第" not in k or "行" not in k]
    ks = sorted(set(ks), key=len, reverse=True)
    return ks[:4]

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
            if ks and any(去饰(k) and 去饰(k) in 去饰(目标行) for k in ks):
                continue
            小节名 = 抽小节名(近句, m)
            if 小节名 and 是标题行(目标行) and 去饰(小节名) and 去饰(小节名) in 去饰(目标行):
                continue
            记["那一行现在是"] = 目标行.strip()[:100]
            if 小节名:
                记["它还说小节是"] = 小节名
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
            目标净 = 去饰(目标行)
            真位 = {}
            for k in ks:
                kn = 去饰(k)
                真位[k] = [i + 1 for i, L in enumerate(目标行们)
                          if kn and kn in 去饰(L) and i + 1 != n]
            记["找的关键词"] = ks
            记["关键词真在哪几行"] = {k: v[:4] for k, v in 真位.items() if v}
            小节名 = 抽小节名(近句, m)
            if 小节名:
                记["它还说小节是"] = 小节名
            # ★★★★★ 红 = 机器百分之百确定的那种坏：**指到空行 / 代码围栏 / 表格分隔线 / 水平线**
            if 空壳.match(目标行):
                记.update({"那一行现在是": 目标行.strip()[:100] or "(空行)",
                         "★": "★★★★★ 指到空行/围栏/表格线 —— ★ 照它去翻，那里什么规则都没有"})
                报["🔴行号空指"].append(记); continue
            if ks and any(去饰(k) and 去饰(k) in 目标净 for k in ks):
                报["✅行号对的"].append({"卡": d, "它说": f"第 {n} 行", "指向": 目标名,
                                     "判法": "关键词落在那一行上"}); continue
            # ★★★★★ 1114-5 新增判法：自述给了小节名，而那一行**就是那个小节的标题** → 判对。
            #   ★★ 这是更严不是更松：没给小节名的、给了但对不上的，★★★ 一律照旧留黄。
            if 小节名 and 是标题行(目标行) and 去饰(小节名) and 去饰(小节名) in 去饰(目标行):
                报["✅行号对的"].append({"卡": d, "它说": f"第 {n} 行", "指向": 目标名,
                                     "判法": f"小节名「{小节名}」对上了那一行的标题"}); continue
            记.update({"那一行现在是": 目标行.strip()[:100],
                     "★": ("★★ %s —— ★ 窗口 ±%d 行内%s → **要人判**" % (
                         ("小节名「%s」和那一行的标题对不上" % 小节名) if 小节名
                         else ("自述没给小节名，关键词也不在那一行上"
                               if not 是标题行(目标行) else
                               "那一行是个标题，但自述没给小节名 → 机器核不了"),
                         窗, "有" if any(去饰(k) and 去饰(k) in 去饰(窗内) for k in ks) else "也没有"))})
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
