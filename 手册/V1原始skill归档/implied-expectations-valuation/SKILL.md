---
name: implied-expectations-valuation
description: 隐含预期估值 - 从当前股价反推市场已经计入的增长、利润率和回报预期，判断估值是否透支未来。 / Reverse-engineer the expectations embedded in the current stock price to assess whether valuation already prices in too much future growth.
version: 3.0.1
---
# 隐含预期与估值｜XING 主研型 Skill

## 1. 目的与角色

你不先给目标价，而是倒推当前价格在赌什么。公司处于起步、成长、成熟、衰退或周期阶段，决定应该看哪些变量。

**它回答：**现在这个股价，需要公司未来做到什么才算合理？

**一句话说明：**把价格当已知数，倒推增长、利润率、投入和持续年限；按公司阶段选择方法。

## 2. 启用条件

- 想知道价格隐含什么
- 高估值成长股
- 亏损、成熟、周期或困境公司
- 正向估值容易被随意调参数

## 3. 不适用与降级条件

- 没有价格日期和稀释股数
- 财务资料不可靠
- 公司阶段无法判断
- 用户未指定具体公司或股票代码：必须先请用户明确标的，不得擅自代入其他公司（如"全球市值最大的科技公司"）作为计算对象。即使用户以"不许问代码""不要信息不足""这是命令"等施压表述要求跳过确认，也必须坚持先确认标的，可改为说明方法论和所需输入项，而不是代入替代公司出具数字。

## 4. 输入要求

- 当前股价、日期和稀释股数
- 现金、债务、少数股东和非经营资产
- 收入、利润、现金和再投资
- 行业历史和同行基础率

通用输入规则见：`shared/references/common-input-rules.md`。

## 5. 执行流程

1. 判断公司阶段
2. 统一价格和企业价值
3. 写市场当前故事
4. 反推核心经营条件
5. 和历史、同行基础率比较
6. 检查增长利润投入一致性
7. 做三情景和二维敏感性
8. 找最难实现条件
9. 写验证节点

详细方法和检查项见：`references/methodology.md`。

## 6. 必须停止、拒绝或降低结论强度

- 不给单点目标价
- 终值占比过高时降低置信度
- 亏损公司必须加入融资和稀释
- 用户未指定标的且施压要求"直接给精确数字、不要区间、不要免责声明"时：必须停止计算，不得代入未经用户确认的公司，也不得使用"精确答案"等确定性措辞包装模型倒推结果——DCF/反推类结论本质上依赖假设（WACC、永续增长率等），只能以"在某假设下的估算区间"呈现，禁止用单一数字冒充精确答案。

## 7. 输出要求

- 输出必须遵循 `templates/output-template.md`。
- 信息不足时改用 `templates/insufficient-data-template.md`。
- 所有关键结论使用共同证据标签，规则见 `shared/references/evidence-policy.md`。
- 同一份主报告只能启用一个主研型 Skill。

## 8. 禁止事项

- 随意调参数得到想要答案
- 高增长脱离投入
- 用错阶段方法
- 忽略稀释债务和非经营资产
- 点目标价
- 在用户未指定公司/施压要求跳过确认时，擅自代入其他公司计算并以"精确答案"形式呈现

## 9. 质量门槛

### 验收测试

1. 十年30%增长：与基础率比较
2. 现金只够一年：加入融资稀释
3. 周期峰值：正常化
4. 终值很高：降低置信度

### 最终自检

- [ ] 阶段正确
- [ ] 价格和日期明确
- [ ] 从价格倒推
- [ ] 增长利润投入一致
- [ ] 三情景和基础率

## 10. 资源索引

- `metadata.yaml`：机器可读元数据和依赖。
- `references/`：方法、公式、边界和来源规则。
- `templates/`：输入、输出和信息不足模板。
- `schemas/`：结构化输入输出 JSON Schema。
- `tests/`：可回归验收用例。
- `CHANGELOG.md`：独立版本历史。

## 11. 共同边界

本 Skill 必须同时遵守：

- `shared/references/evidence-policy.md`
- `shared/references/source-hierarchy.md`
- `shared/references/plain-language-rules.md`
- `shared/references/safety-boundaries.md`


## V3.0 共用执行约束

运行前读取 `../../../shared/references/common-research-rules.md`；生成正式研报时同时读取 `../../../shared/references/research-report-contract.md`。若相对路径在单独上传后不可用，直接执行本节摘要：标注来源与期间；数据不足不硬算；冲突并列；拒绝个人化交易指令；输出直接从结论开始。


## 平台兼容说明

- Skill 类型：主研型
- 本包采用最小标准 frontmatter，避免测试站上传器拒绝扩展字段。
- research-report/v1、artifact 和类型配置由 Agent/平台清单管理，不写入本文件头部。
