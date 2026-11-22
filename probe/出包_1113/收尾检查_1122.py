# -*- coding: utf-8 -*-
"""
收尾检查（★ push 之前跑这一个就够）—— 只读 · rc 0/3 · 🔴 不改 git、不打包、不碰卡
★★★★★ 为什么有这把尺子（1122 第三十二轮立的，★ 错号 #127）：
   ★★ 当天主路在台账里写「包和卡对上了」，**20 分钟后就不成立** —— 卡在别的 chat 手里一直在改；
   ★★★ 一个上午 push 被拒 **3 次**，每次 rebase 之后树都变了，指纹换了**七个**。
   🔴 结论句里不带「量的那一刻」，下一轮就会被当成现在的事实引用。
★★ 本尺子就查三件：
   ① 落后远端没有（落后就别 push，先 rebase）；
   ② 现在树上的卡内容指纹是多少；
   ③ **《92》最后一节里写的那串指纹，和现在是不是同一个** —— 不是 → 🔴 先补记再 push。
🔴 看不见的：★ 它只比指纹这一个数，**不读台账里别的话对不对**（规矩(90)：表对了 ≠ 话对）。
用法：python3 probe/出包_1113/收尾检查_1122.py      # ★ 要顺带跑十四道闸：XING_WITH_GATES=1
"""
import io, os, re, subprocess, sys

ROOT = os.environ.get("XING_SCAN_ROOT", "/home/claude/stock_data")
台账 = os.path.join(ROOT, "手册", "92-进度台账-周一前-每次唤醒先读这份.md")


def 跑(args, **kw):
    p = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=kw.pop("timeout", 120))
    return p.returncode, p.stdout.decode("utf-8", "replace")


def main():
    问题, 提醒 = [], []
    print("=" * 56)
    print("★★★★★ 收尾检查（push 之前跑这一个）")
    print("=" * 56)

    # ① 落后远端没有
    rc, _ = 跑(["git", "fetch", "-q", "origin", "main"], timeout=180)
    if rc != 0:
        提醒.append("★★ `git fetch` 没成（网络？）—— ★★★ 这一项等于没查，**别把「没落后」当结论**")
        后 = 前 = "?"
    else:
        _, out = 跑(["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"])
        前, 后 = (out.split() + ["?", "?"])[:2]
        if 后 not in ("0", "?"):
            问题.append(f"★★★★★ 落后 origin/main **{后}** 个 commit —— ★ 先 `git rebase origin/main`，"
                        f"★★★ rebase 之后**必须重跑本脚本**（树会变）")
    print(f"① 远端：本地领先 {前} · 落后 {后}")

    # ② 现在的指纹
    尺 = os.path.join(ROOT, "probe", "出包_1113", "量卡内容指纹_1121.py")
    if not os.path.isfile(尺):
        print("★★★ 缺 量卡内容指纹_1121.py → 这把尺子没法跑")
        return 3
    _, out = 跑([sys.executable, "-I", 尺])
    m = re.search(r"内容总指纹 SHA-256 = ([0-9a-f]{64})", out)
    现在 = m.group(1) if m else ""
    print(f"② 现在树上卡的内容指纹：{现在[:12] or '?'}…")

    # ③ 台账最后一节写的那串
    if not os.path.isfile(台账):
        提醒.append("★★ 找不到《92》→ 第 ③ 项没查")
    else:
        尾 = io.open(台账, encoding="utf-8").read()[-24000:]
        串 = re.findall(r"[0-9a-f]{64}|`([0-9a-f]{8})…`", 尾)
        串 = [x if isinstance(x, str) and len(x) == 64 else x for x in 串]
        长 = [x for x in re.findall(r"[0-9a-f]{64}", 尾)]
        短 = [x for x in re.findall(r"([0-9a-f]{8})…", 尾)]
        写的 = (长[-1] if 长 else (短[-1] if 短 else ""))
        if not 写的:
            提醒.append("★★★ 《92》最后那一段里**一个指纹都没写** —— ★ 规矩(89)：每轮要量一次并写下来")
        elif 现在 and not 现在.startswith(写的[:8]):
            问题.append(f"★★★★★ **《92》最后写的指纹不是现在这个** —— 台账 `{写的[:8]}…` vs 现在 `{现在[:8]}…`。"
                        f"★★★ 说明写完那一节之后卡又变了 → 🔴 **先往《92》加一条补记**（写明新指纹和是谁改的），再 push；"
                        f"★ 1122 当天这件事发生了 **4 次**。")
        else:
            print(f"③ 台账最后写的 {写的[:8]}… ✅ 和现在同一个")

    if os.environ.get("XING_WITH_GATES"):
        rc, out = 跑([sys.executable, "-I",
                      os.path.join(ROOT, "probe", "出包_1113", "出包_1113.py")], timeout=900)
        尾行 = [l for l in out.splitlines() if l.startswith(("✅", "🔴"))]
        print("④ 十四道闸：" + ("　".join(尾行[-2:]) or f"rc={rc}"))
        if rc != 0:
            提醒.append("★★ 十四道闸没全过 —— ★ 只打包才拦，★★★ 但报的东西要看一眼")

    print("-" * 56)
    for x in 提醒:
        print("🟡", x)
    if 问题:
        print(f"\n🔴 **{len(问题)} 条，先处理再 push**")
        for x in 问题:
            print("  ·", x)
        return 3
    print("\n✅ 可以 push 了（★★ push 完如果又被拒，rebase 之后**重跑本脚本**）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
