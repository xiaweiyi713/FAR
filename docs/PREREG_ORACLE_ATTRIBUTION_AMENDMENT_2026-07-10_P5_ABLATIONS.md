# Oracle attribution amendment：P5 消融实现语义

**对应冻结协议**：`prereg-oracle-v1` / `PREREG_ORACLE_ATTRIBUTION.md`

**发生时点**：H3/H5 的判据已冻结；三个新增消融臂已完成单测与 5 条 FalsiRAG-Bench 离线
smoke，但尚未运行 RAMDocs 350 条正式增强实验，也未读取这些新臂的正式结果。

## 触发原因

原计划给出了三个消融臂的代码骨架，但仍有会影响可解释性的实现歧义：

- “同等激进”是否继续使用正式运行的同一生成器；
- untyped 修订能否读取 typed `suggested_revision`；
- VeraRAG 的“启用 NLI”是否可被称为 NLI-only；
- `flat_claims` 是否允许改变 claim 文本、类型或顺序。

本 amendment 在正式增强重跑前冻结这些语义。原 H3/H5 的 ±0.02 等效界、90% sample-cluster
bootstrap 和“不显著不等于等效”规则均不改变。

## A1：`minus_typed_revision_aggressive`

除修订控制外，decomposer、retriever、typed query、detector、证据、生成器、提示解码参数和样本顺序都与
同提交的 `full` 相同。

冻结处理为：

1. 控制冲突只按 `confidence` 选择，不按 `conflict_type` 排序；
2. `strong -> RETRACT`，`weak -> QUALIFY_UNCERTAINTY`，因此不把所有冲突退化成保守 caveat；
3. 在任何改写前把冲突类型覆盖为通用 `COUNTER_EVIDENCE`，删除 `suggested_revision`；
4. trace 的 `conflict_types=()`，不从旁路泄露类型；
5. 有生成器时继续使用与 `full` 相同的生成器、证据上限、temperature 与 token 上限，但提示不提供类型名；
   无生成器时使用同一强/弱策略的确定性 fallback；
6. 模型仍可从原始证据自行推断事实差异；本臂移除的是显式 typed control signal，不移除证据本身。

因此 H3 比较的是“显式类型控制 + 类型化动作”相对“同生成器的主动 type-blind 修订”的增量。它不应被表述为
完全阻止模型从文本隐式恢复类型。

## A2：`flat_claims`

该臂只把每个 `ClaimNode.depends_on` 置空并重新构造合法 `ClaimGraph`。以下字段必须逐 claim 保持不变：

- claim ID、文本、类型与原 tuple 顺序；
- entities、numbers、time expressions；
- verifiability、confidence 与 source reliability；
- 后续 retriever、query、detector、revision engine 和生成器配置。

不得把 flat 实现成单 claim 合并、重新分句或跳过 claim。H5 只解释依赖边/拓扑约束的增量。

## A3：`minus_typed_detection_nli`

VeraRAG conflict graph 是“规则 -> learned detector -> NLI -> LLM”的分层实现；仅设置
`enable_nli=true` 仍会优先返回规则边，所以不能称 NLI-only。本臂使用独立
`NLIOnlyConflictDetector`：

1. 每对输入固定为 `(retrieved evidence text as premise, claim text as hypothesis)`；
2. 只读取三分类 cross-encoder 的 contradiction probability；
3. 阈值使用冻结配置的 `conflict_graph.nli_threshold`；
4. 命中只产生通用 `COUNTER_EVIDENCE`，不做类型启发式映射；
5. 不运行规则、entity lexicon、Vera graph 或 heuristic fallback；
6. 必须显式设置 `enable_nli=true`、`require_nli=true`；模型缺失、label mapping 不完整、输出形状错误或
   非有限值时失败关闭；不得用 `LABEL_0/1/2` 猜测语义顺序；
7. 每条 conflict 记录模型 ID/revision、阈值、输入方向与 contradiction label index。

该臂成本较高并属于探索性检测对照，不自动加入默认 suite，也不改变 H1/H2 的既有判据。

## 正式运行与判定

H3/H5 的确认性增强运行固定使用 RAMDocs v1 全部 350 条 dev、同一提交、同一冻结 initial-answer bundle、
同一 `ramdocs_qwen` 模型/检索/解码配置，并在同一实现版本下重跑 `full`、
`minus_typed_revision_aggressive`、`flat_claims`。不得拿旧提交的 `full` 与新实现臂直接比较。

- H3：`full - minus_typed_revision_aggressive` 的 RAMDocs EM 配对差及 90% sample-cluster bootstrap；
- H5：`full - flat_claims` 的同一统计；
- 只有完整区间落入 `[-0.02, +0.02]` 才支持等效；
- 区间跨界写“不确定”，完整落在界外写“不等效”；
- 不访问 test，不因方向排除样本，不用 5 条 smoke 结果作研究证据。

正式运行前应以独立 Git 标签冻结本 amendment 与对应实现。正式结果、指纹、功效与失败必须另写报告，不能回改本文。
