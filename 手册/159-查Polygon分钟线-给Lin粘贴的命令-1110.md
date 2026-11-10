# 《159》查 Polygon 那批分钟线能不能用 · 给 Lin 粘贴的命令（2026-11-10）

> ★ 起因：《149》第五节第 6 条 /《149补》第三节第 4 条 —— **先确认 Polygon 全市场分钟线能用**。
> ★★ 在**存全量历史数据那台机器**上粘贴执行，★★★ 把输出推到 GitHub 我直接读。

---

## 零、三秒版

```
★★ 要回答四个问题：**有多少只 · 哪些周期 · 回到哪一年 · 复权了没有**。
★★★★★ 第四个最要紧 —— ★ Gemini 原话：
   「**业界绝对不在未复权数据上跑价格触发类计算。**」
★★ 我们现在手上那 58 只是 `adjustment: raw`（**未复权**），所以才要查这批。
```

---

## 一、粘贴这一段（★ bash，整段一起跑）

```bash
# ★★★ 改成那批 Polygon 数据实际所在的目录
POLY_DIR="$HOME/polygon"      # ← ★ 只改这一行

echo "=== ① 目录在不在、有多大 ==="
ls -d "$POLY_DIR" 2>/dev/null && du -sh "$POLY_DIR" 2>/dev/null || echo "★★★ 这个路径不存在，先确认实际路径"

echo; echo "=== ② 有哪些周期（按文件名猜）==="
find "$POLY_DIR" -type f \( -name "*.json" -o -name "*.csv" -o -name "*.parquet" -o -name "*.csv.gz" \) 2>/dev/null \
  | sed 's|.*/||' | grep -oE "(1|5|15|30|60)min|minute|hour|day|daily|1m|5m|15m|30m|1h|4h" \
  | sort | uniq -c | sort -rn | head -12

echo; echo "=== ③ 有多少只票（按目录名/文件名里的代码猜）==="
find "$POLY_DIR" -maxdepth 2 -type d 2>/dev/null | sed 's|.*/||' | grep -E "^[A-Z][A-Z.]{0,5}$" | sort -u | wc -l
find "$POLY_DIR" -type f 2>/dev/null | sed 's|.*/||' | grep -oE "^[A-Z][A-Z.]{0,5}" | sort -u | wc -l

echo; echo "=== ④ 挑一个分钟级文件，看字段和复权标记（★★★★★ 最要紧的一步）==="
F=$(find "$POLY_DIR" -type f \( -name "*min*" -o -name "*minute*" \) 2>/dev/null | head -1)
echo "样本文件: $F"
if [ -n "$F" ]; then
  case "$F" in
    *.gz)      zcat "$F" | head -c 1200; echo ;;
    *.parquet) python3 -c "import pandas as pd,sys; d=pd.read_parquet('$F'); print(d.dtypes); print(d.head(3)); print('行数', len(d))" ;;
    *)         head -c 1200 "$F"; echo ;;
  esac
fi

echo; echo "=== ⑤ 时间范围（看最早和最晚）==="
if [ -n "$F" ]; then
  case "$F" in
    *.parquet) python3 -c "import pandas as pd; d=pd.read_parquet('$F'); c=[x for x in d.columns if 'time' in x.lower() or 'date' in x.lower() or x=='t']; print('时间列', c); print(d[c[0]].min(), '~', d[c[0]].max()) if c else print('没找到时间列')" ;;
    *.gz)      zcat "$F" | head -2; echo "..."; zcat "$F" | tail -2 ;;
    *)         head -2 "$F"; echo "..."; tail -2 "$F" ;;
  esac
fi

echo; echo "=== ⑥ 有没有单独的复权因子表 / 拆股表 ==="
find "$POLY_DIR" -type f 2>/dev/null | grep -iE "split|adjust|factor|dividend|corporate" | head -8
echo "（★★ 上面空 = 没有单独的因子表，那就要看分钟线本身是不是已复权）"
```

---

## 二、★★★★★ 我要从输出里看什么（★ 你不用管，贴结果就行）

| # | 问题 | 为什么要它 |
|---|---|---|
| ① | 多少只 | ★★ 流动性门槛要「前 1000~1500 只」，58 只不够 |
| ② | 哪些周期 | ★ 《149补》要 1h；有 1min/5min 就能合成 |
| ③ | 回到哪一年 | ★★ 现在这 58 只止于 **2025-12-31**，**没有 2026 年** |
| ④ | **复权了没有** | ★★★★★ **这条决定能不能直接用** —— 未复权就要先复权 |
| ⑤ | 有没有官方开收价 | ★★ Gemini：边界两根要换成**官方开盘/收盘竞价价** |
| ⑥ | 有没有因子表 | ★ 没有的话我用日线的 `split_coefficient` 反推 |

---

## 三、如果那批不能用（★ 备用方案，我这边已经确认可做）

```
★★ 用我们日线里的字段**自己复权**：
   · 日线每根带 `split_coefficient`（★ 实测 NVDA 有两次：2021-07-20 **4 拆** · 2024-06-10 **10 拆**）
   · 和 `dividend_amount`
   → ★★★ 可以反推每天的复权因子，套到 5 分钟线上（★ 除权日 09:30 生效，Gemini 确认的时点）
★★★★★ 但这只解决 58 只那一批的**复权**问题，★★ 解决不了「只有 58 只」和「没有 2026 年」。
→ ★ 所以**先查 Polygon 那批**比较划算。
```
