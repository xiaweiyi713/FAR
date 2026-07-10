# 类型可映射性研究协议（P6 v1）

**状态**：正式人工标注前冻结；实现与标注结果必须在后续提交中产生。

**对应问题**：`PREREG_ORACLE_ATTRIBUTION.md` 的 RQ4/H4。

**冻结日期**：2026-07-10。

## 1. 时间顺序与允许的主张

WS3 边界结果已经在提交 `76bdc7ff30fa3201733573d8fd565971c345663c`（2026-07-09）完成，
而 H4 所在的 `prereg-oracle-v1` 于 2026-07-10 才冻结。因此，用现有 WS3 predictions 做本研究属于
**retrospective mechanism analysis**，即使分析规则在人工标注前冻结，也不能称为 H4 的确认性检验。

允许报告：类型本体在这两个公开 dev 诊断上的人工可映射性、typed−untyped 差异随可映射性的描述性变化、
以及供未来独立数据集检验的效应方向。

禁止报告：H4 confirmed、因果中介、外部泛化、publication-grade human gold，或根据本结果改写既有 WS3
门禁。未来独立数据集上的前瞻性复现才有资格确认 H4。

## 2. 冻结输入与样本

只使用公开 dev 中 `conflict_type != no_conflict` 的 217 条：

| 数据集 | 样本 | 冻结子层 |
|---|---:|---|
| WikiContradict | 150 | Explicit/Implicit × Same/Different 共 4 层 |
| Google CONFLICTS | 67 | outdated 62；misinformation 5 |

Google 的 83 条 no-conflict 样本用于原 WS3 safety，但没有“冲突类型可映射性”，不得塞入 clean 或作为负例。
不访问任何 test/held-out 数据。

冻结文件指纹：

| 输入 | SHA-256 |
|---|---|
| Wiki tasks | `a2c264696f6785a2748a8af214843bfd5c8739cc5e77946243910cd1f205b563` |
| Wiki corpus | `f684ab5008628bc7ab41198d649e9b9794586d372e1c2dc767cefd16129e1d46` |
| Google tasks | `3776cd96b19b1e581d3a4f88d45be8fc73c4d5c153bc876b09cde28d7feb871a` |
| Google corpus | `6beb087fb2e181d1ca59ae5d9aa0d0c92b78e3854d3d22dfec809118595bfb5b` |
| Wiki typed scores | `87cfb1f5baf3513bc0276427f24ac4160f6923a0921075e291fde8ef7e13b56a` |
| Wiki untyped scores | `231973bca0f0ca413ce9692a766c2dd53406e5088996620fc124c968c7f155de` |
| Google typed scores | `d64f0924f50ce515ec82cc07fdf9f5dd357d811042a6a2bc6cc674741bb1467e` |
| Google untyped scores | `4abfb386ca428c859943061031938c7833912607a5477482feb40def617ebbdd` |

## 3. 冻结 FAR 类型本体

标注只能使用以下七类；不得在看到效果后新增或合并类别：

- `temporal`：同一事实槽的时间、日期、版本或有效期冲突；
- `entity`：实体身份、指代、同名对象或实体值替换；
- `numerical`：可比测量、计数、比例或数量值冲突；
- `causal`：因果关系被否定、降格为相关或受混杂限制；
- `source_reliability`：冲突的决断依赖可归因来源的可靠性/权威性；
- `definition`：定义、口径、范围或粒度导致命题含义不同；
- `counter_evidence`：同一命题的**显式直接否定或反例**，且以上六类都不更具体适用。

`counter_evidence` 不是“任何冲突”的兜底；否则本体按定义永远 100% 可映射，RQ4 将失去可证伪性。

## 4. 标注单位与三档判据

单位是一个样本的 question、initial answer/reference answers 与该题全部闭集 evidence。每位 reviewer 必须填写：

- `mappability`：`clean | partial | unmappable`；
- `mapped_types`：上述七类的去重列表；
- `missing_concept`：本体未覆盖的核心关系；
- `rationale`：基于可见文本的简短理由。

机械约束：

- `clean`：恰好一个类型完整决定冲突性质；`mapped_types` 必须恰好一个，`missing_concept` 为空；
- `partial`：至少一个类型覆盖实质部分，但仍缺关键关系或需要未建模组合；`mapped_types` 非空，
  `missing_concept` 非空；
- `unmappable`：七类都不能表达决定性冲突关系；`mapped_types` 为空，`missing_concept` 非空。

多种类型都“可能”适用但没有唯一决定性类型时不得标 clean。对 evidence 不足以判断的样本标
`unmappable`，`missing_concept=insufficient_visible_evidence`，不得静默排除。

## 5. LLM 预标与人工流程

1. 可用冻结模型/提示生成 `machine_prelabels.jsonl`，记录模型 digest、提示 SHA 和原始响应；机器预标不是金标。
2. 两名人工 reviewer 在看不到 machine prelabel、另一 reviewer 标注和 FAR prediction/score 的条件下独立完成
   全部 217 条。
3. 两份完成文件冻结后，第三个 adjudicator 才可同时查看上下文、两份 reviewer 结果和机器预标，逐条给出
   `gold_annotation`。三个非空 ID 必须互异；ID 约束不能证明真实人员独立性，报告必须披露这一点。
4. 不完整、重复、样本集不一致、可见上下文被改、ID 相同或字段违反 §4 时全部失败关闭。

## 6. 一致性与统计

必须报告：

- reviewer 间三档 `mappability` 的 Cohen's κ；
- 七个 mapped type 各自 one-vs-rest κ 及其 macro mean；
- 原始一致率、分歧数、adjudication 后三档/类型分布；
- machine prelabel 对 adjudicated label 的 κ，明确称 model−human agreement，不冒充 human IAA。

不设结果导向的 κ 排除门槛；低 κ 本身是本体边界结果，不能靠删样本修复。

每条样本固定 `delta = typed boundary_score - untyped boundary_score`。输出：

1. 每数据集与合并集的 clean/partial/unmappable 比例；
2. `strict_mappability_rate = clean / n`、`broad_mappability_rate = (clean + partial) / n`、
   `weighted_mappability = mean(clean=1, partial=0.5, unmappable=0)`；
3. 三档内 mean delta 与 2,000 次、seed 1729 的 sample bootstrap 95% interval；
4. 六个冻结 WS3 strata 的 weighted mappability 与 mean delta；
5. 六点 Spearman ρ、未加权 OLS slope/intercept/R²，只作描述性 association，不报告确认性 p-value。

不得把 Wiki 与 Google 不同含义的 absolute boundary score 合并；只允许合并每题已定义的配对 delta。
misinformation `n=5` 必须单列小样本警告。

## 7. 制品与 verifier

计划产物：

- `experiments/type_mappability.py`：`prepare | prelabel | status | analyze | verify`；
- `diagnostics/type_mappability_v1/`：只存输入指纹、空白/完成标注包与机器预标 provenance；
- `reports/type_mappability.{json,md}`：只有双人复核和 adjudication 完整后才能生成；
- `tests/test_type_mappability.py`：覆盖样本选择、schema、κ、delta 对齐、回归和篡改失败关闭。

verifier 必须从冻结输入、完成标注和 score 文件独立重算所有字段与 SHA，并固定输出
`retrospective=true`、`confirmatory_h4=false`、`publication_gold=false`、`test_accessed=false`。
