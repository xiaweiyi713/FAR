# P6-M 跨家族机器本体稳定性审计协议

**状态**：任何 P6-M 模型运行前冻结。

**冻结日期**：2026-07-13。

**替代边界**：本协议不修改或完成 `PREREG_TYPE_MAPPABILITY_2026-07-10.md`
中的人工 P6。原 P6 因没有可用真人 reviewer/adjudicator 而保持未执行；P6-M
只能回答机器评审下的本体稳定性，不能回答人工可映射性。

## 1. 输入、样本与允许主张

复用 P6 已冻结的 217 条公开 dev 样本、七类 FAR 本体、
`clean | partial | unmappable` 判据、typed−untyped 配对 delta 和六个 WS3
strata。不得访问 test/held-out 数据，不得改变原 P6 输入或既有 WS3 结果。

允许报告：跨家族模型对 FAR 本体的操作化可映射性、模型间一致性、模型自身对
提示/evidence 顺序扰动的稳定性、争议覆盖率，以及共识层内 typed−untyped delta
的回顾性描述。

禁止报告：human mappability、human IAA、human adjudication、human gold、
publication-grade gold、H4 confirmed、因果中介或外部泛化。P6-M 不影响任何
既有人工门禁或主结果。

## 2. 冻结评审面板

三个投票角色固定为：

| 角色 | 家族 | provider | 模型 |
|---|---|---|---|
| `J1` | DeepSeek | `deepseek` | `deepseek-chat` |
| `J2` | GLM | `ollama` | `glm4:9b` |
| `J3` | Meta | `ollama` | `llama3.1:8b` |

三者必须独立运行，temperature=0，不能看到另一个 juror 的输出、FAR prediction/
score、analysis strata、上游构造标签或 Qwen machine prelabel。已有 Qwen P6 prelabel
不参与投票，只允许在全部 P6-M 输出冻结后作为第四路留出对照。

本机 Mac 不下载或运行模型。Ollama 模型只允许在授权的远端 GPU 主机运行；若主机
已有任务，P6-M 等待空闲后再启动，不抢占现有任务。

## 3. 双视图与稳定性

每个 juror 对每条样本完成两个隔离视图：

- `view_a`：按协议指纹和 sample ID 确定性打乱 evidence；
- `view_b`：使用等义但不同措辞的 instruction，并反转 `view_a` 的 evidence 顺序。

两个视图都只显示 question、initial/reference answers 和闭集 evidence。每次输出完整
四字段 annotation：`mappability`、`mapped_types`、`missing_concept`、`rationale`。

juror 自稳定的判据固定为：两个视图的 `mappability` 和排序规范化后的
`mapped_types` 完全相同。开放文本 `missing_concept`/`rationale` 不参与逐字稳定性，
但仍必须满足非空和 schema 约束。视图不稳定的 juror 在该样本上 abstain。

## 4. 共识与争议保留

仅稳定 juror 可投票，票值为 `(mappability, mapped_types)`：

- `unanimous`：三个 juror 都稳定且三票相同；
- `majority`：至少两个稳定 juror 给出相同票，但不满足 unanimous；
- `contested`：没有两张相同的稳定票。

P6-M 不使用第四个模型强行仲裁 contested 样本，不把代表性 rationale 冒充 gold。
开放文本按来源保留，供错误分析。任何聚合模型、Dawid–Skene/MACE 或置信度加权只可
作为附加敏感性分析，不能覆盖上述主共识规则。

## 5. 冻结统计

必须报告：

1. 每 juror 的双视图稳定率；
2. `view_a` 与 `view_b` 各自的三档 Fleiss κ、两两 Cohen's κ；
3. 七个 mapped type 的 one-vs-rest 两两 κ 和 macro mean；
4. `unanimous | majority | contested` 数量、稳定投票数和逐样本投票熵；
5. 每个 juror pair 的同票率，作为 leave-one-family-out 敏感性；
6. 共识覆盖率，以及共识样本按数据集/六 strata 的 mappability 分布；
7. 共识层内 typed−untyped delta 的 2,000 次、seed 1729 sample-bootstrap interval；
8. 只有六个 strata 均存在共识样本时才报告六点 Spearman/OLS；否则输出不可估计原因；
9. Wiki Explicit/Implicit × Same/Different 与 Google outdated/misinformation 的分层分布，
   只称 external-label convergent evidence，不把上游标签映射成 FAR gold。

不设结果导向的 κ 或覆盖率排除门槛。低一致性、高 contested 比例或关联反转都必须
原样报告。

## 6. 制品、身份与 verifier

计划产物：

- `far/experiments/type_mappability_machine.py`；
- 三个 juror 目录，每个包含 217×2 条结果、运行身份、模型/配置/提示/输入指纹；
- `reports/type_mappability_machine/` 中的共识 JSONL、JSON/Markdown 报告和 manifest；
- 独立 verifier 从 P6 packet 和三个 juror 原始输出确定性重算全部结果。

所有 manifest/report 必须固定：

- `study_profile=machine_ontology_stability_audit`；
- `human_annotation_replaced=false`；
- `human_iaa_computed=false`；
- `human_identity_verified=false`；
- `publication_gold=false`；
- `retrospective=true`；
- `confirmatory_h4=false`；
- `test_accessed=false`。

缺文件、模型家族重复、模型身份不符、视图缺失、上下文/提示/响应指纹变化、样本集
不完整或任何字段冒充人工证据时，流程必须失败关闭。
