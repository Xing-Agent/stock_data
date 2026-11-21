# -*- coding: utf-8 -*-
"""
量「42 张卡的内容指纹」—— 只读 · rc 0/3
★★★★★ 为什么要这把尺子：《349》给测试组的是 **zip 的 SHA-256**，
   ★★★ 而 `zip -q -r` 把**文件 mtime 写进包里** → ★★ 换个容器重新打包，
   内容一个字节没变，SHA-256 也会不一样（1121 第二十五轮阳性对照已证实）。
   → 🔴 那个 SHA 只能校验**那一个物理文件**，不能校验**卡的内容**。
★★ 本尺子只读文件内容（md5），**不碰 mtime**，所以换容器/重打包都复算得出同一个数。
用法：
   python3 probe/出包_1113/量卡内容指纹_1121.py                  # 只打印
   XING_EXPECT_FP=<64位> python3 ...                             # 对不上 rc=3
   XING_WRITE_MANIFEST=<路径> python3 ...                        # 另存 md5 清单
🔴 看不见的一类（不许缩短）：它只说「内容和记下来那一刻一样」，
   **不说内容是对的** —— 卡里写错的数，它一样算得出干净的指纹。
"""
import hashlib, os, sys

ROOT = os.environ.get("XING_SCAN_ROOT", "/home/claude/stock_data")
卡目录 = os.path.join(ROOT, "skills_v2")


def 算():
    if not os.path.isdir(卡目录):
        print(f"★★★ 找不到 {卡目录}")
        sys.exit(3)
    文件 = sorted(os.path.join(r, f) for r, _, fs in os.walk(卡目录) for f in fs)
    卡 = sorted(d for d in os.listdir(卡目录)
                if os.path.isdir(os.path.join(卡目录, d)))
    行 = []
    for p in 文件:
        with open(p, "rb") as fh:
            行.append(f"{hashlib.md5(fh.read()).hexdigest()}  "
                     f"{os.path.relpath(p, ROOT)}")
    指纹 = hashlib.sha256("\n".join(行).encode()).hexdigest()
    return 卡, 文件, 行, 指纹


def main():
    卡, 文件, 行, 指纹 = 算()
    print(f"卡 {len(卡)} 张 · 文件 {len(文件)} 个")
    print(f"内容总指纹 SHA-256 = {指纹}")
    路 = os.environ.get("XING_WRITE_MANIFEST")
    if 路:
        with open(路, "w", encoding="utf-8") as fh:
            fh.write("\n".join(行))
            fh.write(f"\n\n# 卡 {len(卡)} 张 · 文件 {len(文件)} 个\n")
            fh.write(f"# 内容总指纹 SHA-256 {指纹}\n")
        print(f"md5 清单已写：{路}（{len(行)} 行）")
    期望 = os.environ.get("XING_EXPECT_FP", "").strip()
    if 期望:
        if 期望 == 指纹:
            print("✅ 和记下来的那一份逐位一致")
        else:
            print(f"🔴 对不上　记下来的 {期望}")
            sys.exit(3)
    print("★★ 本尺子只说「内容和记下来那一刻一样」，"
          "🔴 **不说内容是对的**（卡里写错的数一样算得出干净指纹）")


if __name__ == "__main__":
    main()
