# 周期位置与二阶思维｜输入模板

```yaml
skill_id: xing-primary-howard-marks
skill_version: 2.1.0
user_request: ""
company:
  name: ""
  ticker: ""
  exchange: ""
  industry: ""
as_of_date: "YYYY-MM-DD"
report_periods: []
market_quote_date: null
mode: quick|full|single_question
materials:
  public: []
  user_private: []
skill_specific_inputs:
  - 历史估值分位
  - 3、6、12个月一致预期变化
  - 分析师覆盖变化
  - 行业融资、并购和发行热度
  - 信用利差、库存和利润周期
  - 当前企业价值
constraints:
  output_language: zh-CN
  max_length: null
```

缺少字段时不得静默猜测，应在结果中列入 `unknowns`。
