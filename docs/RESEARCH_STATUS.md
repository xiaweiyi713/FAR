# FAR 研究状态与主张边界

**最后更新**：2026-07-10

本文承接 README 中的详细研究状态、阴性结果、停止规则与证据口径。代码是否可运行以测试和发布检查为准；
论文主张是否允许以本文件、预注册、完成度审计和对应冻结证据包为准。

> [!IMPORTANT]
> FAR 当前是 **machine-audited research artifact**，不是 publication-grade human-gold benchmark。
> 300 条 FalsiRAG-Bench 候选标签来自构造规则与机器信号，RAMDocs 使用 upstream 标签；两者都不能替代
> 两名真人独立标注、仲裁或外部保管盲测。项目不主张 FAR 端到端普遍优于现有方法。

## 当前中心主线

RAMDocs 两轮 dev 失败没有被隐藏或换指标“救活”。活动路线已重定位为：

> 在自我纠错检索中，检测与修订分别贡献多少失败质量；任何因果 oracle 主张都必须让干预传播到最终答案，
> 不能只改 metadata 后重打分。

路线见 [PLAN_REDIRECTION.md](PLAN_REDIRECTION.md)，冻结预注册见
[PREREG_ORACLE_ATTRIBUTION.md](PREREG_ORACLE_ATTRIBUTION.md)。

### Oracle attribution 当前进度

- P0：预注册已由 Git 标签 `prereg-oracle-v1` 冻结。
- P1：baseline 重评分精确复现 FAR RAMDocs EM `0.31142857142857144`、coverage
  `0.7509523809523807`、wrong-answer exclusion `0.5685714285714286`。
- Revision label-injection ceiling：9 条 upstream gold/wrong 标签冲突使全体可达 EM 为
  `341/350 = 0.9742857142857143`；341 条 label-feasible 样本上三个指标均为 `1.0`。
- P2-B/P3：观察性 stage-wise trace map 已完成并通过独立重算 verifier。8/8 方法满足
  `post_retrieval_changed_wrong > retrieval_miss`；pooled 差 `+0.3914`，sample-cluster bootstrap
  95% CI `[+0.3554,+0.4275]`。
- 该结果只支持 post-retrieval textual answer-transformation failure。6 个基线没有 detection/action trace，
  因此不能称 causal oracle gap，也不能证明“检测不是跨方法瓶颈”。
- P4：TMLR 工作稿已以该层级重写标题、摘要、贡献、实验设计、8 方法主表、限制、结论和附录 claim ledger；
  readiness gate 绑定 stage trace verifier，PDF 可复现编译且无 overfull box。
- 标签冲突修正完整披露于
  [PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10.md](PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10.md)。

## 状态总表

| 模块 | 当前证据状态 | 不允许升级成的主张 |
|---|---|---|
| FAR 方法 | 主张图、三类查询、类型化检测/修订及 trace 已实现并测试 | 端到端普遍优越 |
| 自足运行时 | BM25 默认后端、离线示例、wheel/sdist smoke 已通过；显式 `vera_*` 可选且失败关闭 | 所有正式模型后端均无需可选依赖 |
| FalsiRAG-Bench | 300 条、五类均衡、175 篇语料；构造校验通过 | 真人金标 benchmark |
| 标签审计 | 机器审计确认 178 条、争议 122 条 | human IAA / adjudicated gold |
| Qwen dev | FAR、6 基线、4 消融完成；typed-vs-untyped 为正，其余混合或负 | blind test / 跨模型结论 |
| WS1 机制归因 | 226 条共同错误唯一分桶；103 条为检出后修订仍错 | 因果 oracle attribution |
| WS2 跨家族 | Mistral/Gemma/Llama 三家族方向 3/3 为正，合并差 `+0.0645` | 高功效确认性复现 |
| WS3 外部边界 | WikiContradict 与 Google CONFLICTS dev 数据已导入并验证；正式 prediction 未运行 | 外部泛化结论 |
| RAMDocs Round 1 | 8 方法 × 350 冻结；FAR 与最强基线 EM 均 `0.3114`，G-A 失败 | FAR 胜出 |
| RAMDocs Round 2 | FAR `0.3086` 对冻结基线 `0.3114`；G-A 再次失败 | 成功方法迭代 |
| 8 方法 stage trace map | T1 `8/8`；T2 `+0.3914`，95% CI `[+0.3554,+0.4275]`；verifier 通过 | 跨方法 detection/action 因果归因 |
| 陪审团/正式矩阵 | 工具存在，但因 G-A 失败未执行 | jury gold / human IAA |
| 盲测 | 技术包、交接协议与评分器已实现；没有外部正式回传 | externally blind evidence |
| FEVER 诊断 | 100 对二分类切片；accuracy `0.72`，召回仍低 | 完整 FAR 外部验证 |

逐项权威审计见 [COMPLETION_AUDIT.md](COMPLETION_AUDIT.md)，当前机器生成状态见
[项目状态快照](../reports/project_status_snapshot.md)。

## 已冻结的主要结果

### WS1：机制归因

零模型调用归因在 226 条 RAMDocs 共同错误上得到：

- `conflict_detected_revision_wrong = 103`；
- `conflict_undetected = 72`；
- typed-vs-untyped 的 34 个正增益样本全部经过 changed revision；
- 移除 typed revision 提高总体平均答案分，但消除了 revision 指标。

这支持“修订路径同时中介局部收益与异质性伤害”的观察性描述，但不等同于有效传播的因果 oracle 曲线。
证据见 [机制归因报告](../reports/mechanism_attribution.md)和
[8 方法 stage trace map](../reports/stage_trace_map.md)。

### WS2：跨家族方向性复现

Mistral、Gemma、Llama 三家族的 typed/untyped 正式臂均完成 60/60：

- 三家族方向 `3/3` 为正；
- 合并 answer-correctness 差 `+0.0645`；
- 分层 exact McNemar `31 vs 9`，`p=0.000680`；
- 家族 bootstrap 95% CI `[+0.0528, +0.0735]`。

预先计算的显著性功效只有 `0.414`，所以结论固定为 `directional_reproduction`，不是确认性跨模型泛化。
证据见 [WS2 报告](../diagnostics/family_dev_v1/family_dev_report.md)与
[功效报告](../reports/power_retrospective.md)。

### RAMDocs 2+4 路线与停止规则

2+4 路线原计划使用 upstream RAMDocs + DeepSeek/GLM/Meta 陪审团 + 作者盲态仲裁，替代无法完成的真人双标注。
它从未被描述为真人 IAA 或 publication-grade human gold。

Round 1：

- FAR EM `0.3114`；最强 Multi-Query 基线 EM `0.3114`；
- 配对差 `0`；bootstrap 95% CI `[-0.0286, 0.0314]`；McNemar `p=1.0`；
- G-A 失败。

Round 2 只改变 FAR 最终答案合并层：

- FAR EM `0.3086`；冻结 Multi-Query 基线 `0.3114`；
- 配对差 `-0.0029`；95% CI `[-0.0314, 0.0286]`；McNemar `p=1.0`；
- 第二次 G-A 失败，触发停止规则。

因此 Phase B、陪审团、作者盲态仲裁、jury rescoring、三系统家族矩阵和 held-out test 均未运行。
协议见 [PLAN_2PLUS4.md](PLAN_2PLUS4.md)，证据包见
[diagnostics/ramdocs_v2](../diagnostics/ramdocs_v2)。

### FEVER 外部迁移诊断

FEVER 切片只继承 SUPPORTS/REFUTES 与金证据；FAR 的类型桶仍是机器启发式，不是类型化金标。
启发式与 VeraRAG NLI detector accuracy 均为 `0.72`；NLI recall 从 `0.30` 到 `0.40`，F1 从
`0.462` 到 `0.533`，但配对 accuracy 差为 0。它是检测器二分类诊断，不是完整 FAR 外部验证。

验证命令：

```bash
uv run falsirag-eval-fever-binary verify \
  --data-dir bench/external/fever_pair_candidates_v1 \
  diagnostics/fever_binary_v1
```

## 证据 profile

### Single-author machine-audited diagnostic

该 profile 使用 LLM 与确定性弱监督信号审计构造标签，允许报告完整 dev 诊断，但强制披露非真人金标、
非外部盲测、功效和负消融。它不降低严格投稿门禁。

```bash
uv run falsirag-solo-release verify diagnostics/solo_v1
uv run falsirag-project-status --verify
uv run falsirag-solo-paper-readiness
```

证据见 [单作者论文就绪报告](../reports/solo_paper_readiness.md)和
[122 条复核优先级表](../reports/solo_human_review_priority.csv)。

### Strict publication profile

严格 profile 仍要求：真人独立标注与仲裁、足够功效的多模型开发矩阵、外部保管盲测回传、可信评分、
发布归档和独立论文审查。目前未满足，所有相关门禁应继续失败关闭。

## 固定的诚实性规则

1. `*_style_reproduction` 只称统一 harness 下的受控复现，不冒充官方实现。
2. RAMDocs upstream 标签和 weak oracle 不称 human gold。
3. Label-injection ceiling 不是可部署修订能力，也不是中心主张的独立证据。
4. 不把“不显著”写成“等效”；H3/H5 只有等效区间完全落入预注册界限才成立。
5. 阴性结果、功效 `0.414`、非盲 dev 和单模型限制必须与任何正向结果并列。
6. 未运行的 jury、held-out 或外部角色不得写成已完成。
7. API key 不得提交；任何曾公开暴露的密钥必须撤销并重新生成。

## 进一步证据入口

- [重定位执行路线](PLAN_REDIRECTION.md)
- [8 方法 stage trace map](../reports/stage_trace_map.md)
- [架构](ARCHITECTURE.md)
- [复现指南](REPRODUCING.md)
- [评测定义](EVALUATION.md)
- [2+4 可追溯性矩阵](PLAN_2PLUS4_TRACEABILITY.md)
- [长期路线状态账本](../reports/longterm_roadmap_status.md)
- [TMLR 结果整合矩阵](../reports/tmlr_result_integration_matrix.md)
- [论文状态](../paper/STATUS.md)
