# 隐含预期与估值｜输入模板

```yaml
skill_id: xing-primary-implied-expectations
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
  - 当前股价、日期和稀释股数
  - 现金、债务、少数股东和非经营资产
  - 收入、利润、现金和再投资
  - 行业历史和同行基础率
constraints:
  output_language: zh-CN
  max_length: null
```

缺少字段时不得静默猜测，应在结果中列入 `unknowns`。
