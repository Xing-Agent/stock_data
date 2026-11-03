---
name: equity-research
description: 仅用于用户明确要求完整正式研报的公司研究、财报复盘和重大事件报告，支持快速、标准、战术深度、深度及投委会级五档。不用于单项事实、营收或利润数字查询、概念解释、计算和无需研报的定向分析；这些直接使用平台工具。
analysis_modes:
  - research
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
  policy: references/08_research_report_output.md
  templates:
    - templates/REPORT_CONTRACTS.md
---

# Equity Research

只在用户要求正式研报时使用。选择一个类型：公司研究 `company_research`、财报复盘 `earnings_review`、重大事件 `event_driven`；选择一个档位，显式要求优先，未指定时选能满足请求的最低档位。

## 工作流

1. 同轮读取[报告契约](templates/REPORT_CONTRACTS.md)与[写作标准](references/08_research_report_output.md)，已加载则复用。围绕用户需求确定少量核心问题，把必写章节映射到具体取证主题。
2. 按下表并行调用首轮工具。索引返回后一次选齐相关原文节点，再批量调用 `retrieve_warm_evidence`。相关原文跨章节复用。
3. 仅为实际缺口或独立研究问题使用条件工具；必需查询取得适用证据或明确不可用状态后成稿。个人资料补充遵循平台的采集阶段安排。
4. 复用步骤 1 的契约与写作标准，直接生成所选档位的一份完整报告。成稿时按写作标准的“引用标记的使用边界”检查每个标记对应的实际断言。正文完成后的审校、修复及发布交给平台；作者不读取审校扩展。

## 档位工具表

| 档位 | 工具与增量 | 首次暖文档取证主题 |
|---|---|---|
| `quick_report` | 首轮 `collect_fundamental_snapshot`、`get_warm_document_index`、`get_market_data`、`get_valuation_metrics`；索引后 `retrieve_warm_evidence` | 最新年度 `annual,count=1` 与最新季度 `quarterly`；业务、经营解释、核心风险和反方依据 |
| `standard` | 继承快速档，增加 `get_consensus_estimates` | 增加行业、经营驱动、预期解释和跟踪主题 |
| `tactical_deep` | 继承标准档；需市场反应时增加事件窗口行情，需事件披露时同批增加 `event` 索引 | 增加竞争与指定财报或事件主题 |
| `deep` | 继承标准档的工具 | 增加竞争、管理层、治理和有来源的反方证据 |
| `full_deep` | 继承深度档；输入齐备后调用 `execute_python` 建立情景模型 | 增加预测假设的披露依据 |

必需工具返回缺口时保留可完成的研究，条件工具未触发不算缺口。快照已提供标准财务、派生指标和一致性结果，直接复用。历史截至研究只请求时点适用的数据：跳过仅支持当前值的估值和共识；行情改用截至该日的历史区间并关闭当前报价，申报与取证沿用同一截止边界。

各档首次仅索引最新年报与季报；只有需要跨年度披露对照且现有材料不足时，才用 `annual,count=2` 补取上年索引。财务历史已由快照提供，不因此预取额外申报。

暖文档只补充结构化结果不能解释的经营驱动、竞争治理、风险和假设依据；财务历史及模型数值由快照等结构化结果负责。每个主题先选最直接的披露，只有该材料不足时才跨文档补充；同一披露跨章节复用，不为章节数量选择近义节点或扩大整章读取。高档位所需主题在首次取证计划中合并。事件日期未知且影响行情窗口时，先确认日期，再请求窗口行情。

## 条件工具

| 工具 | 何时调用 |
|---|---|
| `search_official_web_evidence` | 必须核实政策、监管等第一方事实，或已确认申报缺少必需信息；独立政策问题可首轮并行，申报补缺须等待原文结果 |
| `search_hot_events` | 用户要求近期动态，或核心问题需要近期媒体事件 |
| `get_event_calendar` | 需要确认公告、申报、分红、拆股日期或财报排期；仅支持时间主张，不能支撑经营影响 |
| `get_earnings_call_transcripts` | 用户要求电话会，或必须核实电话会独有的指引 |
| `get_company_segments` | 相关 SEC 索引或原文确实缺少必需的分部披露 |
| `get_macro_indicators` | 已明确允许清单序列、期间及其对公司的传导关系 |
| `search_personal_documents` | 当前报告已选且相关的个人资料，在公开采集结束后批量检索 |
| `execute_python` | 全景档的量化模型，或用户明确要求的额外情景计算；执行前按需读取[情景建模](references/scenario-modeling.md) |

深度档、反方观点和催化剂窗口本身不触发搜索或事件排期查询。
