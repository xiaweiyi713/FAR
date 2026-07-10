# Oracle attribution amendment：P2-B stage-wise trace map

**对应冻结协议**：`prereg-oracle-v1` / `PREREG_ORACLE_ATTRIBUTION.md`

**发生时点**：P1 结果已知；只完成 8 方法字段 schema 审计，尚未计算本 amendment 定义的跨方法聚合、
bootstrap 区间或方向性判据。

## 触发原因

原路线假定 8 方法冻结 prediction 都包含可比的 `claim_graph`、冲突检测与 revision trace。schema 审计发现：

- `far` 与 `far_minus_typed_conflict` 有 `claim_graph`、`predicted_conflict_types`、`revision_action` 和逐 claim
  `revision_trace`；
- 其余 6 个基线只有通用 `evidence_ids`、最终 `answer` 与方法特定 retrieval/reflection trace；
- 基线没有可比的 typed conflict 或 RevisionAction 字段。

把缺失的检测字段当成“未检出”会系统性偏向 FAR；只改这些字段后重评分又违反干预传播门禁。因此 P2 选择
冻结协议 §4 允许的分支 B：**零模型调用的观察性 stage-wise trace attribution**。

## 输入与范围

- 方法：Round 1 suite manifest 固定的 8 方法。
- 样本：RAMDocs dev 全部 350 条，不排除 9 条 gold/wrong label collision。
- 初始答案：`diagnostics/ramdocs_v2/round1/initial_answers/predictions.jsonl`，SHA-256
  `5fbcea9b6b2a6cc1136e87d8bb7a2335feebe8b5e2f5b1f54afcd78a7abbbc6b`。
- 方法 prediction、score、task 与 corpus 必须和 suite manifest / P1 预注册指纹一致。
- 不访问 test，不调用模型，不生成新的系统答案。

## 跨 8 方法的可比分桶

分析单位是 `(sample_id, method)`。按以下固定顺序唯一分桶：

1. `correct`：冻结 `ramdocs_exact_match == 1`。
2. `retrieval_miss`：EM 为 0，且 `evidence_ids` 对 upstream `document_type=correct` 的 recall 为 0。
3. `post_retrieval_unchanged_wrong`：EM 为 0、correct-document recall > 0，最终答案与共享初始答案在
   **去除 `[citation]` 后**经冻结 RAMDocs normalizer 归一化相同。
4. `post_retrieval_changed_wrong`：EM 为 0、correct-document recall > 0，按同一规则归一化后不同。

若样本没有 upstream correct document、ID 集不一致、字段类型错误或无法唯一分桶，分析失败关闭。

`changed` 只表示可观测文本变换，不表示事实被正确修订、模型执行了显式 RevisionAction，或变化由某一阶段因果导致。

## Capability-aware 细分

只在 `far` 与 `far_minus_typed_conflict` 内报告：

- `predicted_conflict_types` 是否非空；
- 逐 claim `revision_trace.changed` 是否为真；
- `revision_action` 分布；
- 在 `ambiguity_misinformation` 弱标签层内的 detection-signal 2×2 描述表。

这部分不外推到其余 6 方法，也不把 upstream 类别称为 human gold。

## 预注册判据

### T1：跨方法 post-retrieval transformation failure

若至少 6/8 方法满足：

`post_retrieval_changed_wrong > retrieval_miss`

则允许写“多数方法的错误更多发生在检索到至少一篇正确文档之后、且最终答案已经发生文本变换的路径”。
否则该跨方法描述不成立。

### T2：pooled cluster-bootstrap 描述

以 sample ID 为 cluster，每次重采样一个 sample 时保留其全部 8 方法，seed `1729`、5000 次 bootstrap。
统计：

`P(post_retrieval_changed_wrong) - P(retrieval_miss)`。

只有 95% percentile interval 下界 > 0 时，才报告 pooled direction；否则写不确定。T2 不能补救 T1 的 6/8 判据。

### 不可由本分析判定

无论 T1/T2 结果如何，本分析都不能证明：

- 检测的 causal oracle gap 小；
- detection 不是跨方法瓶颈；
- action 或 revision 的独立因果贡献；
- implementation gap；
- 人类金标、盲测或部署泛化。

中心主张必须相应拆为：跨方法强度只到“post-retrieval answer transformation failures”；检测与动作的结论只保留为
FAR 两臂的弱标签/trace 观察，等待未来 instrumented replay。

## 输出与完整性门禁

必须输出：

- 8 方法逐桶 count/proportion 与 8×4 表；
- T1 通过方法数及逐方法布尔值；
- T2 点估计与 95% 区间；
- capability matrix，明确哪些方法缺失 detection/action trace；
- FAR 两臂细分表；
- 所有输入 SHA-256；
- `causal_attribution=false`、`publication_gold=false`、`test_accessed=false`；
- 可重新计算并逐字段比对的 verifier。

正式报告文件名为 `reports/stage_trace_map.{json,md}`。若输出或源指纹不匹配，verifier 必须失败。
