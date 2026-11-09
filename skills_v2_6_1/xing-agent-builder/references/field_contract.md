# 观察任务字段与状态

任务：`instance_id`（仅在真实创建后）/ `symbol` / `exchange` / `purpose` / `rule_id` / `rule_version` / `frequency` / `trading_calendar` / `notification_channel` / `authorization` / `start_end` / `pause_condition`。

状态分离（不应将不同维度的状态塞入同一枚举）：
- `config_status`: draft / saved，saved 必须有回执
- `validation_status`: not_validated / validated / invalid（规则真实校验）
- `schedule_status`: disabled / enabled / paused / failed，enabled 必须有回执
- `check_status`: not_run / succeeded / failed（最近一次检查）
- `notification_status`: not_requested / pending / sent / failed，sent 必须有真实投递回执

没有外部平台记录时，只能确认草稿，不自动升级状态。

触发事件：`event_time` / `data_as_of` / `rule_version` / `condition_result` / `notification_status`。同一条件多个触发须定义去重政策；交易时间与通知时间分别记录。

### 去重及审计
`dedupe_key` = (`instance_id`, `rule_version`, `symbol`, `data_as_of`, `trigger_window`)；数据时点、实际执行时间、通知成功时点需分开。`last_checked` 仅来源于真实执行记录，不从配置频率推算。

`notification_authorized` 与 `trading_authorized` 是独立权限；创建/编辑草稿不得默认为通知授权。通知渠道不可用时保持未启用/失败状态，不能暗示已经投递。

`running` 只可在存在实际近期执行记录时作为人类可读展示，不作为替代 `schedule_status` 的持久状态。触发检查与通知的记录必须能用 `instance_id + rule_version + data_as_of + trigger_window` 定位，来源修订应保留版本与重试策略。
