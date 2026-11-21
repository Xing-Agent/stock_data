# -*- coding: utf-8 -*-
"""★★★★★ 闸⑫ 的尺子 —— 查「那几个写进卡的标普数，在 `skills_v2/` 全树一共出现几次」。

★★★ 为什么要有这一道（规矩(84) 配套，★ 1121 第二十四轮装）：
   ★★ 同一天连摔两次，两次都是**闸只盯一份文件**：
     ① 《346》：五个错数「已跟进 V2.6.0 的 42 张卡」—— ★ 新卡自动继承，闸③ 只查 md5 一致，查不出继承；
     ② 《348》：「改一份、铺 42 份就干净」—— ★★ 42×2=84 处，而真分母 **133 处**，
        ★★★ 剩下 49 处在 49 份 `references/entries/*.md` 里抄着逐字相同的一句。
   🔴 ★★★★★ 两次都不是算错，是**从「它只写在某一份文件里」推出来的那句话错了** → 规矩(84)②：
     「只写在某一份」不许当前提，只能当**量出来的结论** → 所以这道闸量的是**全树处数**，不是一份文件的 md5。

★★ 三条 🔴 硬条件（任何一条不过 → 不打包、rc=3）：
   ① **旧值全树 0 处** —— `14.55` · `-34.1%` · `2.0 年` · `-0.38%` · `0.36%`
      （★ 终值见规矩(83)：`13.47` · `-33.7%` · `1.94 年` · `+1.33%` · `0.362%`；
       ★★ `57%` 那一句按 Lin 定的**乙**改成不带数，所以旧值表里**不含** `57%`）。
      ★★★ `0.36%` 不会误伤 `0.362%`（百分号在后面，不是前缀）。
   ② **共用文件每一份都带齐五个新值** —— 份数 == 卡数、md5 唯一（★ 这两项闸③ 也查，这里**带着数再说一遍**）。
   ③ **不许只改一半** —— 凡是写了 `-33.7%` 或 `1.94 年` 的文件，两个数**必须同时在**
      （★★ 那 49 份条目抄的是同一句，少一个就是漏改）。

★ 🟡 只提醒不拦：每个数按「共用文件 / 其他文件」两段列出**文件数 + 处数**（规矩(84)①要求分开列）。
★★ 只读，一个字节都不写仓库。★ 退出码 0 = 没 🔴；3 = 有 🔴。★★★ 按规矩(74)，判断只许有这一份实现。
"""
from __future__ import annotations
import os, io, json, hashlib, sys

ROOT = os.environ.get("XING_SCAN_ROOT") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
# ★★ XING_SCAN_ROOT 只给阳性对照用（★ 在副本上种一行，真仓库不动）；闸里会把它 pop 掉
卡目录 = os.path.join(ROOT, "skills_v2")
共用名 = "common_boundaries.md"

旧值 = ["14.55", "-34.1%", "2.0 年", "-0.38%", "0.36%"]
新值 = ["13.47", "-33.7%", "1.94 年", "+1.33%", "0.362%"]
成对 = ["-33.7%", "1.94 年"]            # ★★ 条件③：这两个必须同进同出


def md5(p: str) -> str:
    return hashlib.md5(io.open(p, "rb").read()).hexdigest()


def main() -> int:
    if not os.path.isdir(卡目录):
        print(f"🔴 找不到 {卡目录}")
        return 3
    文本, 共用 = [], []
    for dp, dirs, fns in os.walk(卡目录):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for fn in sorted(fns):
            if not fn.lower().endswith((".md", ".txt", ".json")):
                continue
            p = os.path.join(dp, fn)
            文本.append(p)
            if fn == 共用名:
                共用.append(p)

    def 数(词):
        共, 他 = {}, {}
        for p in 文本:
            try:
                s = io.open(p, encoding="utf-8").read()
            except Exception:
                continue
            n = s.count(词)
            if n:
                (共 if p in 共用 else 他)[os.path.relpath(p, ROOT)] = n
        return 共, 他

    红, 黄 = [], []
    # ★ 卡数 = skills_v2 下的一级目录数
    卡 = sorted(d for d in os.listdir(卡目录) if os.path.isdir(os.path.join(卡目录, d)))

    # ---- 条件① 旧值全树 0 处 ----
    旧明细 = {}
    for w in 旧值:
        共, 他 = 数(w)
        处 = sum(共.values()) + sum(他.values())
        旧明细[w] = {"共用文件": {"文件": len(共), "处": sum(共.values())},
                     "其他文件": {"文件": len(他), "处": sum(他.values())},
                     "合计处": 处}
        if 处:
            例 = sorted(list(共) + list(他))[:5]
            红.append(f"★★★★★ 旧值 `{w}` 全树还剩 **{处} 处 / {len(共)+len(他)} 个文件** —— "
                      f"🔴 这是「只改一半」：{'、'.join(例)}")

    # ---- 条件② 共用文件份数 · md5 · 五个新值齐 ----
    md5s = sorted({md5(p) for p in 共用})
    if len(共用) != len(卡):
        红.append(f"★★★★★ `{共用名}` **{len(共用)} 份**，卡 **{len(卡)} 张** —— 🔴 对不上")
    if len(md5s) != 1:
        红.append(f"★★★★★ `{共用名}` 分叉成 **{len(md5s)} 种 md5** —— 🔴 不是全卡同一份")
    缺 = {}
    for p in 共用:
        s = io.open(p, encoding="utf-8").read()
        少 = [w for w in 新值 if w not in s]
        if 少:
            缺[os.path.relpath(p, ROOT)] = 少
    if 缺:
        例 = sorted(缺.items())[:3]
        红.append(f"★★★★★ **{len(缺)} 份**共用文件缺新值 —— 🔴 "
                  + "；".join(f"{k} 缺 {'、'.join(v)}" for k, v in 例))

    # ---- 条件③ 成对的两个数不许只出现一个 ----
    集 = {}
    for w in 成对:
        共, 他 = 数(w)
        集[w] = set(共) | set(他)
    只一个 = (集[成对[0]] ^ 集[成对[1]])
    if 只一个:
        红.append(f"★★★★★ **{len(只一个)} 个文件**只写了 `{成对[0]}` / `{成对[1]}` 里的一个 —— "
                  f"🔴 那 49 份条目抄的是同一句，少一个就是漏改：{'、'.join(sorted(只一个)[:5])}")

    # ---- 🟡 新值分段画像（规矩(84)① 要求分开列）----
    新明细 = {}
    for w in 新值:
        共, 他 = 数(w)
        新明细[w] = {"共用文件": {"文件": len(共), "处": sum(共.values())},
                     "其他文件": {"文件": len(他), "处": sum(他.values())},
                     "合计处": sum(共.values()) + sum(他.values())}
    黄.append("★★ 新值分段处数（★ 不设硬阈值：加卡会让处数变，"
              "🔴 要拦的是「旧值还在」和「只改一半」，不是「处数等于某个固定值」）：" +
              " · ".join(f"`{w}` 共用 {d['共用文件']['处']} 处 / 其他 "
                         f"{d['其他文件']['处']} 处（{d['其他文件']['文件']} 个文件）"
                         for w, d in 新明细.items()))
    黄.append("★★★★★ 本尺子看不见的一类：**别的写法说同一件事** —— "
              "★ 比如把 `-33.7%` 写成「三成三」「约 34%」「三分之一」，★★ 本闸一个都报不出来；"
              "★★★ 所以 🔴 0 只能读成「这五个字面串干净」，★ 不是「卡里没有错数」。")

    报 = {"★卡数": len(卡), "★扫了几个文本文件": len(文本),
          f"★{共用名} 份数": len(共用), "★md5 种数": len(md5s),
          "🔴旧值残留": 旧明细, "★新值分段": 新明细,
          "🔴": 红, "🟡": 黄}
    出 = os.environ.get("XING_OUT")
    if 出:
        io.open(出, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1))
    print(json.dumps(报, ensure_ascii=False, indent=1))
    return 3 if 红 else 0


if __name__ == "__main__":
    sys.exit(main())
