# FAR typed conflict control 机制归因 (WS1)

> 本报告是冻结 dev 制品的零模型调用重分析；不是新金标、真人 IAA、盲测或 G-A 重开。

## RAMDocs 共同错误的最早失败阶段

| 主桶 | 数量 |
|---|---:|
| `retrieval_miss` | 4 |
| `conflict_undetected` | 72 |
| `conflict_detected_revision_wrong` | 103 |
| `answer_set_incomplete` | 35 |
| `answer_set_overfull` | 12 |
| `format_em_mismatch` | 0 |

- 上游正确文档可用性: available=348, unavailable=2；无正确文档题按注册的最早上游失败规则进入 `retrieval_miss`。

## 预注册假设结论

| 假设 | 状态 |
|---|---|
| H-upstream | `not_supported` |
| H-conflict-shape | `not_supported` |
| H-metric | `not_supported` |
| H-component | `not_supported` |

## dev 组件归因

- typed 相对 untyped 的正向连续分数样本: 34。
- 增益路径: detected_no_changed_revision=0, changed_revision=34, other=0。
- 五臂翻转以 answer_correctness ≥0.8 定义样本正确；连续分数差同时保留。

## 适用前提

1. 相关正确证据必须先被检索到；typed control 不能修复零正确文档的检索结果。
2. 冲突形态必须能映射到结构化类型并被检测；不同冲突分布需单独披露。
3. 检出后的修订策略不能抵消检测/查询阶段收益；detection 与 revision 必须分开评估。
4. 全集合 strict 判分与描述性 partial credit 必须并列报告，但后者不得追溯性改写门禁。

## 结论边界

这些结论只刻画机器审计 dev 与 upstream-labelled RAMDocs dev 的机制边界。它们不支持端到端普遍优势、真人金标、外部盲测或多模型泛化声明。
