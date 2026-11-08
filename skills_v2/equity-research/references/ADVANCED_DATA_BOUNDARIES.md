# Advanced Data Boundaries · 条件读取（复杂取证才加载）

本文件只在 **历史 PIT、跨源冲突、数据异常或非标数据** 时加载一次；用于约束风险，不是必须逐步执行的流程。

## 证据主权
- 财务报表/原始业绩：SEC 冷数据；经营策略/客户/分部与治理：SEC 申报/IR 暖数据；行情和市值：行情市场快照；估值倍数和每股指标：平台 valuation-metrics 已返回字段；宏观：平台允许的系列；私人文件只能作为额外独立证据或方法要求。
- `get_company_segments` 的商业 Provider 备援只在 SEC 暖文档缺失时使用；`as_of_date` 严格历史请求不可用当前修订的分部/地区值代替，应返回 `unavailable_for_strict_pit`。
- 一致预期 `provider=auto` 时 FMP 优先、不可用时 Alpha Vantage；单一期间不得跨来源拼接或平均；留存财年/季度、GAAP口径、估值/证券口径、Provider、estimate as-of 与 retrieved-at。平台不支持任意历史一致预期快照；“上一季预期差”没有披露前快照，标明无法检验。
- 新闻和网页历史窗口 `published_at <= as_of_date` 仅可称 `publication_filtered`，不可称完整可回放历史 PIT。没有可核验发布时间的网页不用于历史证据。
- ALFRED 仅使用平台允许清单内的 vintage；非白名单 BEA/BLS/Census 不用二手页面替代 PIT。
- 股息、P/B、股利、EV/EBITDA 等原样使用平台返回的估值字段；不由模型推算缺失字段。PEG 或复杂指标仅在平台确定性计算且输入证据可核验时引用。

## 冲突和异常
1. 核对 ticker、交易所、拆股与复权、币种、单位、财年截止日、季度/TTM、会计定义。
2. 对证据 ID 保留 Provider、取证时间和冲突状态；原值均留存，不静默选最大/最新。
3. 只消费平台已计算的 YoY/QoQ、Z-score、MAD、检查结论；缺计算能力就标缺口。
4. 异常归因可查并购/剥离、减值、汇率、产品 mix、税率、会计变更、营运资本；分为 `CONFIRMED_EVENT` / `PLAUSIBLE_MULTI_FACTOR` / `DATA_ERROR_CONFIRMED` / `UNRESOLVED`。
5. `UNRESOLVED` 的异常不得支持精准预测、强因果解释和强估值结论。

## Source-specific 状态
平台工具 docstring/schema 高于此文件的示例；工具未开放、不在白名单或用户未授权时只能记录缺口，不能临时调用未经许可的数据渠道。
禁止用当前数据模拟历史准确信息；禁止在财务事实中混合用户上传的猜测或用附件覆写平台证据。
