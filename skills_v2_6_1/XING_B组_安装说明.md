# B 组 Skill · 独立安装说明

版本：V2.6.1

总压缩包为分发容器，**不能作为单张 Skill 安装**。先解压总包，再将以下六个 ZIP 按需独立上传。每个独立 ZIP 根目录直接包含 `SKILL.md`，以及该 Skill 自己的 `references/` 与 `templates/`。

| 安装文件 | Skill 名称 | 功能 |
|---|---|---|
| `01_xing-quote.zip` | `xing-quote` | 单股行情解释 |
| `02_xing-screener.zip` | `xing-screener` | 股票筛选与结果统计 |
| `03_xing-review.zip` | `xing-review` | 持仓复检 |
| `04_xing-condition-engine.zip` | `xing-condition-engine` | 条件规范化与真值判定 |
| `05_xing-skill-builder.zip` | `xing-skill-builder` | 通用规则草稿与验证 |
| `06_xing-agent-builder.zip` | `xing-agent-builder` | 单标的观察任务配置 |

## 启用建议

在隔离的测试专家中逐张上传、逐张测试；全量开启时应确认主入口只路由当前已安装且有权限的功能 Skill。缺少平台行情、股票池、持仓源或调度接口时，相应能力必须按文档降级为真实可交付的行情解释、条件草稿或待确认配置，不声称已执行。

上线验收建议：每张三次独立调用，检查目标卡是否实际加载、参考文件是否读取、数据时点是否一致、结果是否完整及是否取得真实运行回执。`condition-engine` 的逻辑判定测试应使用完整、缺失、规则非法和未执行四组输入。
