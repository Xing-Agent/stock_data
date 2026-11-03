# 安全边际与克制｜输入模板

```yaml
skill_id: xing-primary-klarman-margin-of-safety
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
  - 当前股价与稀释股数
  - 现金、债务和表外义务
  - 正常化现金流或资产
  - 公司类型和融资需求
  - 税、少数股东和变现成本
constraints:
  output_language: zh-CN
  max_length: null
```

缺少字段时不得静默猜测，应在结果中列入 `unknowns`。
