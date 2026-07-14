# FAR 研究状态与主张边界

**最后更新**：2026-07-14

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
  readiness gate 绑定 stage trace、P5 注册报告与可从跟踪原始证据重算的 P6-M verifier。P5 的 H3
  `uncertain`/H5 scoped `equivalent` 和 P6-M 的 15/217 共识、202 contested 阴性结果均已进入主文及
  TMLR 附录；15 页 PDF 可复现编译且无 overfull box 或未解析引用。包含 P13 的当前公开可移植证据已冻结为
  [`paper-v2`](https://github.com/xiaweiyi713/FAR/releases/tag/paper-v2)，并通过远端下载后的隔离验证；
  `paper-v1` 继续保留为 P12 历史快照。
- 标签冲突修正完整披露于
  [PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10.md](PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10.md)。
- P5：注册的远端 3×350 RAMDocs dev 消融已完成并通过零模型独立 verifier。full EM 为 `0.3057`；
  `minus_typed_revision_aggressive` 为 `0.3086`，full-minus 差 `-0.0029`、90% CI
  `[-0.0229,+0.0171]`，越过预注册等效下界，因此 H3 固定为 `uncertain`；`flat_claims` 为 `0.3057`，
  full-minus 差 `0.0000`、90% CI `[-0.0057,+0.0057]` 完全落入 `[-0.02,+0.02]`，因此 H5 为
  `equivalent`。这是上游标签 dev enhancement，不是人类金标、held-out/test 或 publication gold。见
  [P5 报告](../reports/p5_ramdocs_ablations.md)、[P5 runbook](P5_EXECUTION.md) 与
  [P5 amendment](PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10_P5_ABLATIONS.md)。
- P6：类型可映射性协议已在人工标注前冻结，217 条不可见 score 的空白包、机器预标、三人安装、κ、
  描述性 association 与独立重算 verifier 已实现。远端 Qwen 机器预标已完成 217/217，并以 221 次总尝试、
  prompt/raw-response/attempt provenance 回传安装；本机未运行模型。因 WS3 结果早于 H4，当前分析固定为
  retrospective，不能确认 H4。因无法取得真人，双标/第三人仲裁分支现已退出活动范围，空白协议和
  `ready_to_analyze=false` 仅为未来严格人工主张保留。见
  [P6 execution](P6_EXECUTION.md) 与
  [P6 协议](PREREG_TYPE_MAPPABILITY_2026-07-10.md)。
- P6-M：三名远端 juror 的 217×2 双视图运行均完成，失败尝试为 0；J1/J2/J3 稳定率分别为
  `50/217`、`88/217`、`24/217`。只有 `15/217`（`0.0691`）形成机器共识，其中 unanimous 1、
  majority 14、contested 202；view A/B Fleiss κ 分别为 `0.1666` 和 `-0.0408`。一个冻结 strata
  零共识，因此六点 association 不可估计。确定性 verifier 返回 `valid=true`。结果只证明该机器面板
  对等义提示/evidence 顺序高度敏感，不能报告总体可映射率，也不能替代严格人工 P6；该阴性结果同时
  作为已接受无真人 profile 的终止证据，不再继续寻找模型“同位替代”。见
  [P6-M 报告](../reports/type_mappability_machine/type_mappability_machine.md)、
  [P6-M execution](P6M_EXECUTION.md) 与
  [P6-M 协议](PREREG_TYPE_MAPPABILITY_MACHINE_2026-07-13.md)。
- P11：在冻结的 60 条 Qwen dev prediction 上完成零模型 revision-delta 审计。FAR raw/typed
  delta F1 为 `0.145/0.096`，高于 untyped conflict arm 的 `0.093/0`；但 CRAG-style 与
  Vanilla raw delta 更高（`0.307/0.264`），去掉 refutation query 也提高到 `0.194`。因此它只支持
  typed control 的可审计性，并强化 mixed/negative component 结论；该指标是 construction-reference
  依赖的词面编辑诊断，不是语义正确率、真人 gold 或新推理证据。定义与边界见
  [REVISION_DELTA_METRIC_AUDIT.md](REVISION_DELTA_METRIC_AUDIT.md)。
  在冻结 WS2 predictions 上，Mistral/Gemma/Llama 的 raw typed-minus-untyped delta 差为
  `+0.0133/+0.0524/+0.0536`，合并 `+0.0398`、family-cluster 95% CI
  `[+0.0133,+0.0536]`；typed delta 合并 `+0.0816` `[+0.0353,+0.1137]`。这是事后
  transport sensitivity，不是预注册 WS2 主指标或外部分布泛化。
- P12：冻结 revision trace 的词面目标对齐审计已完成。Qwen FAR trace delta F1 为 `0.0823`，
  仅 `15/60` 完整覆盖 construction target，`19/60` off-target、`12/60` 无词法目标编辑。
  typed-minus-untyped trace delta 为 `+0.0481`、95% CI `[+0.0084,+0.0998]`；Mistral/Gemma/
  Llama 三家族方向均正，合并 `+0.0232` `[+0.0064,+0.0355]`。但 any-target-hit 没有改善，
  因此只支持 typed control 的窄目标对齐信号，并确认 revision reliability 仍低。见
  [REVISION_TRACE_FIDELITY_AUDIT.md](REVISION_TRACE_FIDELITY_AUDIT.md)。
- P13：冻结选择性修订可行性审计已完成。保留错误初始答案的 whole-answer soft F1 为
  `0.9784`，60/60 均越过旧 `0.8` 阈值但 revision-delta F1 为 0，证明该阈值不能作为安全门。
  typed/generic delta F1 为 `0.1454/0.0723`；逐条使用 reference 选择三臂最优也只到 `0.1618`，
  比 always typed 高 `+0.0164`。confidence `>=0.90` 的 31 条 conditional delta F1 反降至
  `0.1386`，仅 5/31 target-complete、25/31 collateral。它是同一 dev 上的事后诊断，不是
  deployable selector、prospective calibration 或 causal policy effect。见
  [SELECTIVE_REVISION_FEASIBILITY_AUDIT.md](SELECTIVE_REVISION_FEASIBILITY_AUDIT.md)。
- P14：针对 P13 的阴性结论，已在任何新输出产生前冻结 reference-free、post-generation
  accept/reject 实验。它从尚未用于正式模型运行的 train 行中确定 60 calibration + 60 evaluation，
  每类各 12 条且 dependency group 完全隔离；远端 operational packet 只含问题和初始答案等五个字段。
  100 个候选策略、coverage `[0.25,0.75]`、`+0.03` fidelity enrichment、collateral/target-complete
  安全条件和 calibration-fail 即停止规则均已固定。v1 因逐样本卸载模型过慢，在 10/120 时按用户
  要求暂停；未形成 predictions/manifest/report，也未查看或评分内容，永久退出分析。结果盲 v2
  amendment 要求从零重跑、独立 cache/output、跨样本 keep-alive 和精确新 tag。正式运行只能在
  `windows-gpu` 再次空闲、Qwen digest 匹配后启动；当前尚无 P14 结果，不得提前写入论文。见
  [P14 preregistration](PREREG_SELECTIVE_ACCEPTANCE_2026-07-14.md) 与
  [performance amendment](AMENDMENT_SELECTIVE_ACCEPTANCE_PERFORMANCE_2026-07-14.md)。

## 状态总表

| 模块 | 当前证据状态 | 不允许升级成的主张 |
|---|---|---|
| FAR 方法 | 主张图、三类查询、类型化检测/修订及 trace 已实现并测试 | 端到端普遍优越 |
| 自足运行时 | BM25 默认后端、离线示例、wheel/sdist smoke 已通过；显式 `vera_*` 可选且失败关闭 | 所有正式模型后端均无需可选依赖 |
| FalsiRAG-Bench | 300 条、五类均衡、175 篇语料；构造校验通过 | 真人金标 benchmark |
| 标签审计 | 机器审计确认 178 条、争议 122 条 | human IAA / adjudicated gold |
| Qwen dev | FAR、6 基线、4 消融完成；typed-vs-untyped 为正，其余混合或负 | blind test / 跨模型结论 |
| P11 revision delta | 冻结 Qwen 与 WS2 prediction 的 raw/typed 词面编辑诊断完成；typed-vs-untyped 跨家族方向复现，但广义 Qwen 基线 raw delta 高于 FAR | 预注册确认性结果、语义正确率、真人验证或 FAR 普遍优越 |
| P12 revision trace | 冻结 Qwen/WS2 claim trace 的目标对齐审计完成；typed trace F1 方向复现，但 Qwen FAR 仅 15/60 完整覆盖、19/60 off-target、12/60 无词法目标编辑 | 因果 action oracle、语义修订正确率、真人验证或可靠自动修订系统 |
| P13 selective revision | 冻结 typed/generic/preserve 三臂的 metric conflict、reference arm envelope 与 confidence replay 完成；简单阈值不能筛出更高保真修订 | 已校准/可部署 selector、因果 policy effect、held-out risk-coverage 或语义正确率 |
| P14 selective acceptance | 新 train 证据、dependency-group 隔离 60/60、reference-free 生成后 controller、校准停止规则和 verifier 已预注册；10-row v1 未评分退出，result-blind keep-alive v2 等待 GPU 空闲后从零执行 | v1 结果或复用、已有 v2 结果、pre-execution selector、语义安全、外部验证、因果 policy effect 或 test 结论 |
| P5 新消融 | 3×350 注册 dev 运行与独立 verifier 完成；H3 `uncertain`，H5 `equivalent` | H3 等效、NLI 检测增益、human/test/publication-gold 结论 |
| P6 可映射性 | 217/217 远端机器预标已回传；严格人工分支 inactive，`ready_to_analyze=false`，不在当前无真人 profile 待办 | H4 确认、human IAA 或正式人工可映射率 |
| P6-M 机器稳定性 | 三家族均 434/434；仅 15/217 共识、202 contested；verifier 通过；阴性结果关闭无真人 profile | 总体人工可映射性、human IAA/gold、H4 确认或严格人工 P6 已完成 |
| WS1 机制归因 | 226 条共同错误唯一分桶；103 条为检出后修订仍错 | 因果 oracle attribution |
| WS2 跨家族 | Mistral/Gemma/Llama 三家族方向 3/3 为正，合并差 `+0.0645` | 高功效确认性复现 |
| WS3 外部边界 | 两数据集正式 dev 运行与 verifier 已完成；typed−untyped 数据集级结果近零 | 全局外部迁移或端到端优越性 |
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
证据见 [WS2 报告](https://github.com/xiaweiyi713/FAR/blob/artifacts-v1/diagnostics/family_dev_v1/family_dev_report.md)与
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
[diagnostics/ramdocs_v2](https://github.com/xiaweiyi713/FAR/tree/artifacts-v1/diagnostics/ramdocs_v2)。

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

### Accepted no-human redirection profile

当前活动口径以已验证的 P6-M 阴性结果结束：路线本身已完成，不再等待找不到的真人，也不再追加模型
模拟复核或仲裁。原 P6 人工包保持 `ready_to_analyze=false` 并退出活动队列；只有未来明确需要总体人工
可映射性、human IAA 或 adjudicated human gold，且真实人员可用时才重新开启。

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
