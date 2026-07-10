# Oracle attribution 预注册（v1）

**状态**：已冻结（以 `prereg-oracle-v1` 所指提交为准）

**计划冻结标签**：`prereg-oracle-v1`

**冻结日期**：2026-07-10

**分析对象**：RAMDocs v1 dev；8 个同一 harness 下的方法复现；不访问 test
**核心限制**：RAMDocs 标签来自 upstream，`publication_gold=false`；它们不是本项目人工金标。

本文在任何 oracle 结果计算前冻结研究问题、假设、干预语义、主要指标、判定规则与停止条件。冻结后若需改变这些内容，必须新增带日期的 amendment；不得改写本文件或移动原判据。

## 1. 研究范围与固定输入

### 1.1 样本与方法

- 样本：`bench/external/ramdocs_v1/splits/dev.jsonl` 的全部 350 条 dev 样本。
- 语料：`bench/external/ramdocs_v1/corpus.jsonl`。
- 方法：`vanilla_rag`、`multi_query_rag`、`crag_style_reproduction`、`self_rag_style_reproduction`、`reflective_rag`、`counterrefine_style_reproduction`、`far`、`far_minus_typed_conflict`。
- 冻结运行：`diagnostics/ramdocs_v2/round1/`。所有 `*_style_reproduction` 仅表示统一 harness 下的受控复现，不表示官方实现。
- 禁止使用 RAMDocs test、后见人工修订标签或新模型输出来选择分析规则。

冻结输入指纹：

| 输入 | SHA-256 |
|---|---|
| dev tasks | `412e65b77dec89da9358499c39a714876606958373f3ae0f284a5b2fb20d6a9f` |
| corpus | `219269fedcdc21c9bd87b045a5afd1e7ce60c22ea21f4c1e8ded9c7658d61496` |
| Round 1 suite manifest | `3da14fe405e2bd8061787b16185f3238c8f0c07e37ef734144be76135e7e6f2a` |

### 1.2 结果变量

主要结果变量是冻结的 `ramdocs_exact_match`：预测必须包含全部 normalized gold phrases，且不包含任何 normalized wrong phrase。

次要结果变量是：

- `gold_answer_coverage`；
- `wrong_answer_exclusion`；
- 每阶段的失败质量与条件失败率；
- 方法间异质性。

`unsupported_sentence_rate` 只作为词法支持代理报告，不参与核心假设判定。`misinformation_conflict_detected` 是弱标签诊断，不得表述为人工验证的事实判断。

## 2. 研究问题与预注册假设

### RQ1 / H1：检测是否是主要瓶颈？

H1：在可比较的样本—方法单元中，检索成功后“已检测但最终修订错误”的失败质量高于“应检测但未检测”的失败质量。主判据为按 sample ID 聚类 bootstrap 的两者差值 95% 区间下界大于 0；否则 H1 不成立或证据不足。

### RQ2 / H2：修订瓶颈是否跨方法一致？

H2：8 个方法中至少 6 个满足修订失败质量大于检测失败质量。必须逐方法报告，不得只给 pooled 结果；不足 6 个则“跨方法一致”主张被否定。

### RQ3 / H3：typed 信息是否有独立于修订激进度的贡献？

H3：控制修订激进度后，`full - minus_typed_revision_aggressive` 的 EM 差异等效于 0。等效界预先设为 ±0.02，使用 90% 聚类 bootstrap 区间；仅当完整区间落在等效界内才支持等效，跨界则记为不确定，不把“不显著”写成“无效”。

### RQ4 / H4：类型本体覆盖是否解释 typed 增益？

H4：`clean | partial | unmappable` 的可映射性越高，typed 相对 untyped 的配对增益越大。若可用独立数据集/预注册分层少于 5 个，仅报告描述性结果，不进行相关或回归的确认性推断。

### RQ5 / H5：claim graph 结构是否有独立贡献？

H5：`full - flat_claims` 的 EM 差异等效于 0；沿用 H3 的 ±0.02 等效界与 90% 聚类 bootstrap 判据。若区间未完整落入界内，结论必须写为不确定。

H3–H5 属于增强阶段，不得用 P1 的 baseline/ceiling 结果提前宣称支持。

## 3. 四个 oracle 箑子的冻结语义

固定因果顺序为：`retrieval -> detection -> action -> revision`。记原系统输出为 `B`，累计干预输出为 `O_R`、`O_RD`、`O_RDA`、`O_RDAV`。主要指标增量不截断为正数；若某级下降，保留负值。

### 3.1 Oracle retrieval（R）

用 RAMDocs upstream `document_type=correct` 文档替换该样本的检索结果，然后以冻结的同方法检测、动作与修订实现重新计算最终答案。该算子只允许读取文档类型，不允许读取 gold/wrong answer phrases。

### 3.2 Weak-oracle detection（D）

在 R 的输出状态上，用 upstream 类别与文档类型派生的弱冲突目标替换检测结果，然后以冻结的同方法动作与修订实现重新计算最终答案。报告和论文必须始终使用“weak oracle”或“upstream-derived weak labels”，不得简称 human gold。

### 3.3 Oracle action（A）

在 RD 的状态上，用在结果解封前冻结的确定性 `conflict state -> RevisionAction` 映射替换动作选择，再以冻结的同方法修订实现重新计算最终答案。若无法在不读取 gold/wrong answer phrases 的前提下定义唯一理想动作，则 A 级停止，不能用事后选择的动作补齐。

### 3.4 Oracle revision / label-injection ceiling（V）

把最终答案替换为按任务文件顺序、去重后以 `" ; "` 连接的全部 `gold_answers`。此级允许读取 gold phrases，因此只是评分管道与标签一致性的 ceiling/sanity check，不是可部署能力，也不是“修订是瓶颈”的独立证据。

## 4. 干预传播门禁（防循环论证）

当前冻结 predictions 的 EM 评分只读取 `answer`。因此仅修改 `evidence_ids`、`predicted_conflict_types` 或 `revision_action` 而不重新生成答案，会使 R/D/A 三级按构造与 baseline 相等，并把全部表观增益推给 V。该做法无资格称为端到端 oracle attribution。

R、D、A 中每一级在正式运行前必须同时满足：

1. 干预后的状态实际传入后续阶段；
2. 后续阶段产生新的、带 provenance 的最终 `answer`；
3. 非当前 oracle 阶段不得读取 gold/wrong phrases；
4. 重新计算使用冻结的实现、模型标识、提示与解码设置；
5. 对每条样本记录输入、输出、干预字段及源码/配置指纹；
6. 单测证明“只改元数据、不改答案”的伪干预会被拒绝。

若为了保持零模型调用而不能满足上述门禁，则产物必须改名为 **stage-wise trace attribution**，只报告观察性失败质量与条件率，不使用 `oracle gap`、`causal contribution` 或“端到端增益”措辞。

## 5. P1：baseline + revision ceiling 的确认性验收

P1 只实现两个层级：

- `baseline`：不做任何干预；
- `oracle_revision`：仅做 §3.4 的 label injection。

验收标准全部预先固定：

1. 以 `sample_id` 对齐，拒绝重复、缺失或额外 ID；禁止按行号静默 zip。
2. baseline 重新评分必须在绝对误差 `1e-12` 内复现冻结 FAR report 的三个答案指标：
   - EM `0.31142857142857144`；
   - coverage `0.7509523809523807`；
   - wrong-answer exclusion `0.5685714285714286`。
3. revision ceiling 在全部 350 条上必须达到 EM、coverage、wrong-answer exclusion 均为 `1.0`；否则停止并报告 label collision 或实现错误。
4. 输入 prediction/task 不得被原地修改。
5. 未实现 R/D/A 时必须 fail closed；不得返回与 baseline 相同的占位分数。
6. P1 的 ceiling 不用于 H1–H5 判定，只证明数据对齐、评分复现与上界构造正确。

## 6. P2/P3 的分析与报告规则

- 主分析单位为 sample ID；跨方法统计按 sample ID 聚类，保留同一问题上 8 个方法的相关性。
- 固定报告每方法的 baseline、各累计级、相邻增量、样本数、95% 区间和负增量。
- H1 同时报告 pooled 与逐方法结果；H2 只按预注册的“至少 6/8”判定。
- 固定输出所有失败桶、缺失/不可判定计数以及 weak-label 覆盖率。
- 不因结果方向改变阈值、方法集合、样本集合、operator 顺序或主要指标。
- 多重检验：H1/H2 是共同核心结论；只有两者都通过才允许写“跨方法修订瓶颈”。H3–H5 分别报告，不借其中任一结果补救 H1/H2。

## 7. 停止、否证与诚实性规则

出现以下任一情况即停止相应确认性分析：

- 任一输入指纹不匹配；
- baseline 不能复现冻结 report；
- ID 集不完全一致；
- operator 使用了未声明的 gold 字段；
- R/D/A 未传播到最终答案；
- 模型/提示/解码设置无法冻结或追溯；
- 样本被结果导向地排除。

下列结果会否证或显著削弱中心主张：

- H1 的区间未表明修订失败质量大于检测失败质量；
- 少于 6/8 方法满足 H2；
- 有效传播后的 detection oracle 增量稳定大于 revision 前的残余；
- 结论只在 FAR 成立而不在多数对照方法成立。

所有发布物必须并列披露：machine-audited/upstream 标签性质、`publication_gold=false`、非盲 dev、样本数、功效限制、阴性结果，以及 label-injection ceiling 的非部署性质。

## 8. 冻结与 amendment

冻结提交只包含路线与本预注册，不包含 oracle 实现或结果。标签 `prereg-oracle-v1` 指向该提交。冻结后：

- 实现性澄清可追加 `docs/PREREG_ORACLE_ATTRIBUTION_AMENDMENT_<date>.md`；
- amendment 必须说明触发原因、发生在何种结果访问之前/之后、影响哪些假设；
- 原文件、原标签与原判据保持不变。
