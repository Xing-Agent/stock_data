---
name: equity-research
description: XING 正式美股研报的研究编排与撰稿，覆盖公司研究、财报复盘、事件研究的五档 Markdown 报告；普通答疑不触发。
analysis_modes:
 - research
 - mixed
workflow:
 protocol: research-report/v1
 artifact: research_report
capabilities:
 - financial-history
 - issuer-disclosure
 - market-data
 - news-events
 - consensus-estimates
 - company-segments
 - valuation-metrics
 - industry-macro
 - deterministic-calculation
contracts:
 audit_extension: references/09_publication_quality_gate.md
reports:
 policy: SKILL.md
 templates:
 - templates/REPORT_CONTRACTS.md
---

> **能力分类：常用工具（非大师）**。按需调用一次；不绑定人物、不强制练习/复盘/决策流程，不主动推荐交易方法。


# Equity Research · XING v3.0（快路径 + 质量门禁）

**目标**：正式研报在完整性、公司专属度、证据可追溯性不降级的前提下，避免每次按 01→09 连续读取。
当前文件包含从规划到写作的**全部常态执行指令**。通常只需再读取一次 `templates/REPORT_CONTRACTS.md`（五档章节/字符数权威契约）。**不要求**读取其他 reference 才能开始采集或成稿；条件分支以外不读取。平台已提供的证据、计算与路由信息优先复用。

## 0. 启用与快速路由（本地完成，不读取文件）
- 仅用户明确要求**正式研报**时启用；短事实、问答、单项计算或“大师陪我学习”不启用。
- `analysis_type` 只可取 `company_research` / `earnings_review` / `event_driven`；`report_mode` 只可取 `quick_report` / `standard` / `tactical_deep` / `deep` / `full_deep`。
- 用户已指明类型/档位则直接用，不重复路由。未指明时按目标与证据范围选可完整交付的**最低合适档位**；不得自动升级至 `full_deep`。
- 财报复盘默认 `earnings_review` + `tactical_deep`；明确“快速分析”用 `quick_report`；明确“深度研究”用 `deep`。这只是缺省映射，显式要求优先。
- 单报告只选一个主类型与档位，多意图并入子章。当前不支持独立附件研报、两公司比较研报或方法驱动报告，不要偷换成相邻模板。风险看板交给 `risk-dashboard`。

## 1. 一次性最小研究计划（上下文内，不生成中间 JSON）
先写出 3–5 个必须回答的公司专属问题，再逐项绑定：关键主张→最小证据→期间/来源→缺失时的降级→停止条件。覆盖真实相关的业务驱动、客户/产品/地区、成本/资本、竞争/替代、催化剂、风险、跟踪指标；与主张无关的不采集。
- 若平台返回 `security_identity.sec.sic/sic_description`，用作行业分类，不把银行、保险、REIT 当工业企业机械套 EV/EBITDA 或通用 FCF 模型。
- `quick_report`：财务快照、公司业务与风险披露、市场快照、适用估值；`standard` 加有根据的市场预期；`tactical_deep` 围绕当期及事件窗口；`deep` 加治理、竞争与反方；`full_deep` 须有足够预测及估值输入。**档位不等于每种工具都必须调用**。

## 2. 取证：按批次执行，不按文档分步往返
以运行时工具 docstring / JSON Schema 为唯一工具参数契约：
- `financial-history` 财务历史及平台确定性派生值；`issuer-disclosure` SEC/IR 申报、经营/治理/指引；`market-data` 最新报价与必要日线；`valuation-metrics` 官方适配的估值字段；`consensus-estimates` 相同期间、相同口径预期；`company-segments` 分部/地区/KPI，SEC 暖文档优先；`news-events` 相关事件；`industry-macro` 有传导机制的宏观。
- 同类独立请求尽量走工具 batch-first；只重试失败项，**不得**因另一子项失败而重复成功请求。每个调用都要能回答上述某一个问题；所需证据到达可支持主张的终态后停止。
- SEC 冷数据支撑财务事实，暖披露支撑经营解释，行情支撑价格，新闻不替代申报，一致预期不跨 Provider 拼接；个人附件不替代公开财务数据。
- 当前 provider 的一致预期不可冒充**历史 as-of** 预期；未经核验的拆股、证券单位、币种、TTM/财年口径不能进计算。
- **只有**出现历史 PIT 截止日、跨 Provider 冲突、非标字段异常、复杂数据源问题时，读取一次 `references/ADVANCED_DATA_BOUNDARIES.md`；常态不需要。
- **只有**用户授权、平台为 mixed 模式且选择了个人资料时，在公开采集关闭后读取一次 `references/ATTACHMENT_BOUNDARY.md`，批量取得资料；禁止把用户方法文件当公司事实。

## 3. 证据整理、异常、计算（常态内联）
保留公司与证券身份、来源、截至时点、财务期间、币种、单位、会计口径和可靠引用；冲突**并列**，不静默覆盖。季度/财年规模比例只做诊断，不能当同比或年化。
增长率、利润率、FCF、CAGR、TTM 等只解释**平台已验证的确定性计算结果**；模型不心算财务核心指标、P/E 或 EPS 拼接。没有 Z-score/MAD/异常检验返回，就不能声称算过；发现不可归因异常时降低或撤回相关强结论。
将主张分为 `FACT_SUMMARY`、`CALC_INTERPRETATION`、`INFERENCE`、`SCENARIO`、`VARIANT_VIEW`；数字和关键事实必须有来源，推断须标条件，结论须有反方/证伪。用户方法只决定看什么，不是公司事实。`deep/full_deep` 至少有实质性 Variant View。

## 3.1 2026-11-04 生效的呈现安全门

- 首屏必须先告知最主要的代价、失败情景或风险边界；独立“风险分析”章节必须在“投资逻辑”之前，章节以更新后的 `templates/REPORT_CONTRACTS.md` 为准。
- 引用任一方法的定量参数时逐条输出来源档位及能核实的出处；没有一手原文、缺验收记录则显示“待核实/待验证”，不得因方法名气直接标原著。
- 任何技术方法第④栏只允许教学展示时，不得进入买卖点、止损、仓位或交易契约风险计算。

## 4. 一次成稿
读取**一次** `templates/REPORT_CONTRACTS.md` 取得唯一档位的章节、上限、风险字段、催化剂窗口和跟踪指标；**若该契约已在当前上下文，不要重复读取**。完整报告由同一作者生成，首行 `# `，使用 Markdown；有唯一数据来源/缺口、结论状态、免责声明。所有核心段落锚定具体产品、客户、业务线、竞争、行业指标或监管暴露，避免跨公司通用模板。
- 没有同期间同口径、披露前可得的预期，不称“超预期”；未确认事件只能作不确定情景；数据不足时给真实边界而不是补空话。
- 不输出研究计划/主张图/Schema、内部状态或协议标记；平台负责缓冲、续写、基础审校、修复、发布。
- 禁止个性化买卖/持有评级、目标价、杠杆、仓位与保证收益；不得冒用投资大师背书。

## 5. 强制边界：作者≠审校器
`references/09_publication_quality_gate.md` **仅由平台在正文完成后加载**作为专项审校扩展；作者不得读取，也不得自发二次审校/发布。公开采集阶段最多两次简短进度说明。

## 6. 性能与质量自检（无额外 Read）
- 先复用证据上下文；严格分支加载；每个路径至多一次，禁止循环“翻 9 个文件”。
- 请求批量、一次整理、一位作者；任何数据缺口只影响相关主张，不触发无限补全。
- 数字带口径与来源；公司专属性；反方及失效条件；档位契约符合；未知和口径冲突明确；不出现交易指令。
- 无法判断 ≠ 证据为零；质量不能用降低证据要求换低 token。

## 7. v3 · 运行时工具读取预算和停止条件
- **预注入优先**：平台若已按 `report_mode` 注入选中档的 `report_contract`，作者**不要再打开** `REPORT_CONTRACTS.md`；若没有，只读取一次完整契约。预注入内容必须由该模板自动生成，不能由多个地方手动维护。
- **规则 Read 预算（非财务数据工具）**：常态 0–1 次（模板）；历史 PIT 或混合附件按命中分支各再加 1 次；专项审校由平台独立执行，不占作者预算。
- **取证停止条件**：每个核心判断已经具备来源/期间/口径和至少一个有力反方；新增工具只会重复已知事实时停止，不盲目补齐与公司无关的数据维度。核心论点缺资料时降级说明，不用模型猜数字。
- **实测**：记录 task_id、report_mode、read_reference_count、financial_tool_count、request_rounds、input/output tokens、retry_count、report_gate_failures、source_mismatches。减少 Read 不等于减少财务工具，也不能用更少引用换速度。
- **兼容性**：此版本废弃的旧 01–08 引用若被后端硬编码，必须由适配层迁移；不要向模型暴露指向不存在的旧路径。

## 当前规范（2026-10-20；v7 决策流程 / v13 策略手册）
- **唯一有效引用**：用户交互/记录/退出状态以《大师策略决策流程 v7》为准；方法规则、禁令、归属、证据与允许用途以《大师策略手册 v13》为准。此前 v6/v11、v10 条目与示例均属兼容历史，不得覆盖当前修订。实施细则：`references/shared/V7_V13_RUNTIME_RULES.md`。
- 模型负责解释与受控编排，数据读数、参数校验、回测、订阅及成交核验只能来自确定性引擎和实际授权状态。**2026-11-04 策略审核结论：技-3、技-12 的历史有限实测不代表用途第④栏获批；包括这两项在内的全部 14 张技术面方法卡当前仅供教学/研究展示，不进入实盘买卖点、止损、仓位或交易契约风险计算。此前候选表述均为历史背景，不构成授权。**
- 先给事实和原因，再显示成立/不成立/未知、离门槛差多少、数据时间/周期/来源/规则版本、作者禁令与方法代价；拒绝个性化下单不等于拒绝讲解方法。禁止无分母主观概率、邀功归因、标的合成打分和默认推荐；原著 F-Score/RS Rating 等可复算原生分数可保留。
- 若涉及温斯坦，必须显式展示**日线/周线各自口径**，不要在主状态权威口径未拍板时把日线 150MA 称作未限定的“温斯坦阶段二”；周线 w_ 字段不能误报缺失，未收盘周线条件不能算满足。未解决的口径问题显示“待策略组确认”，不替策略组决策。
- 原著写死的规则不可当可调优产品参数；XING 自设参数标注 XING·待校准。数值示例/回测统计只在有相应版本与分母的已验证数据显示时引用，不能硬编码进用户实时结论。
---

> **XING V2.3 接入附注**：本方法是 V2 研究视角，不覆盖 `xing-main` 的统一边界，不抢占 `xing-fundamental-analyst`、`xing-technical-analyst`、`xing-screener` 等模块的正式数值判定。执行前按需参阅 `references/shared/method_integration_contract.md`；该路径按本集成包根目录解析。若引用的底层工具未实际接通，必须降级说明，不得模拟计算结果或历史回测证据。

## 共用边界

本卡的研究规则与表达边界，以 `references/shared/common_boundaries.md` 为**唯一来源**。
该文件 38 张卡共用一份；**不要改写、不要复制到本卡正文里**。
