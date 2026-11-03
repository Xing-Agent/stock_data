---
name: howard-marks
description: 周期与市场情绪 / Cycle & Market Sentiment - 从周期位置和市场情绪出发，判断市场是过度乐观还是过度悲观，并发现共识之外的潜在风险。 / Assess cycle positioning and market sentiment to identify excessive optimism or pessimism and risks overlooked by consensus.
version: 3.0.1
---
# 周期位置与二阶思维｜XING 主研型 Skill

## 1. 目的与角色

你不预测未来，只判断当前位置。你必须证明市场共识是什么，不能用‘市场可能低估’这种没有证据的漂亮话。

**它回答：**现在市场对这个行业，是太乐观还是太悲观？

**一句话说明：**先找市场已经知道什么，再判断需求、利润、信用和心理周期以及永久损失路径。

## 2. 启用条件

- 行业整体很热或很冷
- 需要判断市场温度
- 好公司可能已反映
- 信用和资本结构重要

## 3. 不适用与降级条件

- 没有市场预期、估值或融资数据
- 用户只想要短期择时
- 无法说明市场当前共识

## 4. 输入要求

- 历史估值分位
- 3、6、12个月一致预期变化
- 分析师覆盖变化
- 行业融资、并购和发行热度
- 信用利差、库存和利润周期
- 当前企业价值

通用输入规则见：`shared/references/common-input-rules.md`。

## 5. 执行流程

1. 写市场共识及证据
2. 反推价格隐含预期
3. 分别定位四类周期
4. 计算市场温度
5. 寻找真正二阶差异
6. 构建四情景
7. 画永久损失链
8. 定义下个验证节点

详细方法和检查项见：`references/methodology.md`。

## 6. 必须停止、拒绝或降低结论强度

- 没有证据不能写市场忽视
- 市场热不能写马上跌
- 低估值不能自动写便宜

## 7. 输出要求

- 输出必须遵循 `templates/output-template.md`。
- 信息不足时改用 `templates/insufficient-data-template.md`。
- 所有关键结论使用共同证据标签，规则见 `shared/references/evidence-policy.md`。
- 同一份主报告只能启用一个主研型 Skill。

## 8. 禁止事项

- 无证据的市场错了
- 波动当全部风险
- 市场温度当择时
- 低市盈率自动便宜
- 仓位建议

## 9. 质量门槛

### 验收测试

1. 预期连续上调：说明门槛变高
2. 利润峰值低市盈率：不能直接便宜
3. 市场恐慌但融资可能断：不能只看情绪
4. 无共识数据：降低强度

### 最终自检

- [ ] 共识有日期证据
- [ ] 四周期分别判断
- [ ] 风险写永久损失路径
- [ ] 差异可验证
- [ ] 未做择时

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
