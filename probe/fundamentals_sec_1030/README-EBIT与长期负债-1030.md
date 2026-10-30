# EBIT 与长期负债 · 从 SEC 补齐 · 2026-10-30 · 给回测会话

> **三秒版:不接 Polygon。直接从 SEC 原始财报补,300 只里非金融的 239 只:EBIT 有 233 只(原来 177/250),长期负债有 216 只(原来 140/250),剩下没数的 18 只里 15 只就是公司本身没负债。⑤ 质量复利、⑦ 融合大师可以跑了。**
> **★ 两件要你们注意:① 金融/地产 61 只标了「不适用」,这两个策略里要排除它们;② 「没有长期负债数」≠ 缺数据,名单里写了原因,建议按 0 处理(TXT、PCAR 除外)。**

## 文件
| 文件 | 内容 |
|---|---|
| `sec_ltd_ebit_pit_1030.csv.gz` | 主表,75,359 行,公布日 2014 起。每份财报里的每个数都留着(包括后来重述的旧数) |
| `sec_missing_nonfin_1030.csv` | 非金融里没取到数的 19 只,逐只写原因 |
| `build_sec_fund.py` | 生成脚本,读同目录的 `sec_companyfacts_300_1030.json.gz`(上次已推) |

## 一 · 怎么用(时点)
- **`filed` = 公布日,回测里只能在 `filed` 之后用这个数**。同一 `period_end` 会有多行(原报 + 后面财报里的对比数/重述),按「信号日之前最晚 `filed` 的那条」取
- 年度用 `form` 以 10-K 开头 且 `period_start`→`period_end` 约 12 个月的行;季度同理约 3 个月(10-Q 里也有 6/9 个月的累计数,注意按期间长度筛)
- ★ `fiscal_year` / `fiscal_period` 是**那份财报**的财年,不是这个数所属的期间(10-K 里的上年对比数也标本年)。**用 `period_end` 判断期间**
- 单位:美元原值

## 二 · 字段名按什么顺序取(`source_tag` 记了用的哪个,`basis` 是大白话标签)

**长期负债**(时点数,`period_start` 为空),同一份财报同一日期先找到哪个用哪个:
| 顺序 | SEC 字段 | basis | 行数 |
|---|---|---|---|
| 1 | LongTermDebtNoncurrent | noncurrent | 12,883 |
| 2 | LongTermDebtAndCapitalLeaseObligations(YUM 这类) | noncurrent_incl_capital_lease | 4,807 |
| 3 | LongTermNotesPayable / SeniorLongTermNotes / OtherLongTermDebtNoncurrent | notes_noncurrent / senior_notes / other_noncurrent | 920 |
| 4 | 总数 − 一年内到期(LongTermDebt − LongTermDebtCurrent 等) | derived_total_minus_current | 140 |
| 5 | 只有含一年内到期的总数、没拆分(房屋建筑商等不分流动/非流动的报表) | **total_incl_current_no_split** ← 偏大一点 | 2,976 |
| 6 | 可转债 / 长期授信 | convertible_notes / credit_line | 615 |

**EBIT**(期间数):
| 顺序 | 怎么来 | basis | 行数 |
|---|---|---|---|
| 1 | 财报上的营业利润 OperatingIncomeLoss | reported_operating_income | 47,002 |
| 2 | 税前利润 + 利息支出,同一份财报同一期间 | **derived_pretax_plus_interest** ← 推算 | 6,016 |

## 三 · 覆盖(按 10-K 计)
| | 原来(repo 里的 fundamentals.json,250 只) | 现在 · 原 250 只 | 现在 · 全 300 只 | 现在 · 非金融 239 只 | 非金融 2016–2024 每年都有 |
|---|---|---|---|---|---|
| EBIT | 177 | 241 | 287 | **233** | 198 |
| 长期负债 | 140 | 226 | 265 | **216** | 149 |

- pilot_50 来的 50 只原来没有基本面,这次一起补了
- 「每年都有」偏低,主要是中途上市/退市的公司,不是缺数据

## 四 · 没取到的(非金融)
- **本身没负债**(15 只):BMI、ISRG、VEEV、ABMD、OFLX、VNDA、TRUE、ENTA、LIXT、MPWR、COLM、FF、BBW、MSB(信托)、WLKP(只欠母公司) → 建议长期负债按 0
- **★ 真缺**:TXT、PCAR(工业和金融分部分开报,用了自定义字段)—— 两只都是大盘,建议这两个策略里先剔除,别填 0
- MTR:SEC 查不到;EBIT 另缺 TMHC、BBW、PCAR、MSB、MTR
- 另外 OCSI、FRC 本来就不在 SEC 数据里(FRC 是向 FDIC 报的)

## 五 · 金融/地产为什么「不适用」
`financial_sector = true` 的 61 只(Financial Services 35 + Real Estate 26):银行、保险的利息就是主营,营业利润和「长期负债」的含义跟工业公司不是一回事,硬算 EBIT/负债率会排出一堆误判。表里照样有数(能取到的都留着),但**质量复利、融合大师应排除这些行**。
