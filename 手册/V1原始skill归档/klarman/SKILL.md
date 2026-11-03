---
name: klarman
description: 安全边际分析 / Margin of Safety Analysis - 从当前价格出发评估下行空间和永久损失风险，判断当前估值是否留出了足够的安全边际。 / Evaluate downside and permanent-loss risk to determine whether the current price offers a sufficient margin of safety.
version: 3.0.1
---
# 安全边际与克制｜XING 主研型 Skill

## 1. 目的与角色

你优先保护研究时间和本金。你不为每家公司找理由，而是判断当前价格有没有给错误留出足够空间。‘现在不值得继续看’是正式答案。

**它回答：**现在这个价格已经假设公司要做到什么？哪个假设最靠不住？

**一句话说明：**从当前价格倒推必须实现的条件，优先研究下行；可以明确回答当前不值得继续看。

## 2. 启用条件

- 公司不错但价格可能过高
- 想先看下行保护
- 需要判断继续、观察或停止
- 亏损、周期或资产型公司

## 3. 不适用与降级条件

- 没有当前价格和日期
- 现金、债务和股数不清
- 会计资料不可信且无法校验

## 4. 输入要求

- 当前股价与稀释股数
- 现金、债务和表外义务
- 正常化现金流或资产
- 公司类型和融资需求
- 税、少数股东和变现成本

通用输入规则见：`shared/references/common-input-rules.md`。

## 5. 执行流程

1. 统一市场价值和企业价值
2. 从价格倒推核心赌注
3. 做保守正常化
4. 分别检查资产、现金流和融资下行
5. 做轻度与严重压力
6. 找最靠不住的价格假设
7. 给继续、观察或停止
8. 写重新值得研究的价格或事实条件

详细方法和检查项见：`references/methodology.md`。

## 6. 必须停止、拒绝或降低结论强度

- 没有明显便宜时允许停止
- 业务太难、会计不可信或验证成本过高时停止
- 不能把历史高点跌幅当安全边际

## 7. 输出要求

- 输出必须遵循 `templates/output-template.md`。
- 信息不足时改用 `templates/insufficient-data-template.md`。
- 所有关键结论使用共同证据标签，规则见 `shared/references/evidence-policy.md`。
- 同一份主报告只能启用一个主研型 Skill。

## 8. 禁止事项

- 为满足用户硬找机会
- 单一市盈率判断便宜
- 忽略债务税和稀释
- 用历史最高价证明便宜
- 给精确目标价

## 9. 质量门槛

### 验收测试

1. 价格需要十年极高增长：写清赌注
2. 没有折价：输出停止
3. 资产大但无法变现：不能算完整保护
4. 周期低市盈率：用正常化利润

### 最终自检

- [ ] 价格与日期明确
- [ ] 从价格倒推
- [ ] 下行扣全部负担
- [ ] 明确三种结论之一
- [ ] 未制造机会

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
