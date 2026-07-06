# FAR 外部冲突边界测绘预注册（WS3）

- 状态：**已注册 v1（2026-07-06），首个 WS3 prediction 前冻结**。
- 上位路线：`docs/PLAN_LONGTERM_OPTIMIZATION.md`，活动 SHA-256
  `91eb3205fe127271bc5f4882025243d9974a711e311ef074fcbde09aa86e7cf7`。
- 选型依据：`reports/boundary_benchmark_selection.md`。只选 WikiContradict 与 Google
  CONFLICTS；FaithEval、ClashEval、ConflictBank 按许可/划分红线排除。

## 1. 研究问题

在两个冲突形态明显不同的外部公开 dev 诊断上，typed control 相对匹配的 untyped arm
在哪些条件下方向为正、为零或造成伤害？本研究产出“基准特征 × typed 效应”的边界矩阵，
不做全局胜负门禁，不重开 RAMDocs G-A，也不把外部数据标签称为 FAR 的真人 IAA。

WS1 已关闭 upstream-only、metric-masking 和 detection-only 三个简单解释。WS3 因此测量
完整 typed control（检测 + 修订）的异质效果，不把任何正结果追溯性归因给单一组件。

## 2. 冻结数据与导入

| 基准 | 冻结来源 | 样本 | 任务 | 导入 manifest SHA-256 |
|---|---|---:|---|---|
| WikiContradict | HF revision `c20e361f985ed480a659b35d98b49f2311fcd174`，MIT | 150 | 初始 answer1；目标覆盖两个矛盾 context 各自支持的 answer1/answer2 | `b3b3b80c44600579e15cfe4e9071040cfd99cc3d49ed716ee9dd603435a07765` |
| Google CONFLICTS | Git commit `81ba921dd684a93db41a7e9dda6b6a7c67348a88`，Apache-2.0 | 150 | 初始答案为上游正确答案；目标是在 outdated/misinfo/no-conflict context 下保持正确答案 | `ec12941a2e98461219858d56a6a07545ba4d5ac70eca96dac2f6148b4ccb86e5` |

Wiki 配额固定为 Explicit/Different 72、Implicit/Different 41、Explicit/Same 24、
Implicit/Same 13。Google 固定 outdated 62、misinformation 5、no-conflict 83；无唯一正确
答案的 complementary/opinion 行排除。两者 seed=2718、split=`dev`，剩余上游行不补跑。

运行时每题只能检索该题自己的闭集文档，禁止跨题语料泄漏。项目的 FalsiRAG/RAMDocs
held-out/test 永久不触；FaithEval 官方 test 也不触。

## 3. 模型、方法与运行纪律

- 模型固定 Qwen3.5 9B Ollama tag `qwen3.5:9b`，digest
  `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`。
- 配置固定 `experiments/configs/qwen_boundary.yaml`，SHA-256
  `d3a36b59d02eb4c086e87445d0757d466a25e9f3d2428d4bdc9a36bae9acc979`；检索、NLI、
  temperature 与 F1/WS2 正式栈一致，cache 在 D:。
- 两臂仅 `far` 与 `far_minus_typed_conflict`；不增加端到端基线，不改 prompt/参数。
- 每基准先跑两臂各 5 条固定 calibration，只验证结构和 checkpoint；随后各跑 150 条。
  calibration 不计入统计。正式运行器强制 Wiki → Google、calibration → formal，输出 D:，
  可续跑，无 Round 2；推荐入口为 `falsirag-boundary run-all --output-dir <D:输出根>`。
- 首个正式 prediction 前要求预注册与实现存在于干净、已推送提交；之后不允许偏离。

## 4. 冻结评分

文本先使用 RAMDocs 英文数字 normalizer。对 Wiki，每个 reference answer 若作为连续 token
片段出现在最终答案中记一次命中，`boundary_score = hits / 2`；binary success 要求两个答案
均命中。冲突提示词命中率另作描述性指标，不进入主分数。

对 Google，`boundary_score` 为最终答案相对唯一 `correct_answer` 的冻结 lexical soft F1；
binary success 要求 `boundary_score >= 0.8`。该设计测答案保持，不奖励改写成检索中的错误值。

每基准的机制主结果均为 150 个逐样本 `typed boundary_score − untyped boundary_score`：

- 按冻结 strata 的 paired percentile bootstrap，2,000 次、seed=1729，报告均值差与 95% CI；
- binary success 的双侧 exact McNemar；
- 两基准 McNemar p 统一做 Holm 校正；
- 按 Wiki explicit/implicit、same/different 与 Google outdated/misinfo/no-conflict 全部披露。

两个 benchmark-specific 分数不可合并成一个总胜负数字。G-B 是完整性门，不是显著性门。

## 5. 运行前假设网格

| ID | 条件 | 适用前提 | 预期 | 事后机械判定 |
|---|---|---|---|---|
| B-W-explicit | Wiki explicit | 两个答案表面可检索，冲突显式但来源等可信 | typed 正方向 | explicit 子集均值差 >0 记 direction matched，否则 contradicted |
| B-W-implicit | Wiki implicit | 需跨句推理，类型分类学匹配较弱 | 弱于 explicit | `delta_explicit > delta_implicit` 记 matched，否则 contradicted |
| B-G-outdated | Google outdated | 时间冲突可映射 `temporal`，正确初始答案已知 | typed 正方向 | outdated 子集均值差 >0 记 matched，否则 contradicted |
| B-G-misinfo | Google misinformation | 可映射 source reliability，但 n=5 | 不可判定、只描述 | 永久 `descriptive_only`，不得用于正/负主张 |
| B-G-safe | Google no-conflict | 无冲突时 typed 不应过度修订 | 非劣于 -0.03 | typed−untyped >= -0.03 记 safety matched，否则 safety violated |

显著性只决定证据强弱，不改变上述方向判定。某子集出现正结果不得弱化 RAMDocs 双失败。

## 6. G-P 与解释

沿用 Qwen dev 不一致率 19/60 与目标效应 +0.078，n=150 的 exact McNemar 功效为 0.348
（20,000 次、seed 2718 Monte Carlo 0.344），低于 0.60。本研究级别固定为
`directional_boundary_mapping`：null 不证明无效；正方向也只说明该公开 dev 分布上的边界，
不升级为普遍外部验证。

全 null → “已证实增益仍限构造对齐 Qwen dev”；仅 Wiki 正 → “等可信显式冲突可能受益”；
仅 Google outdated 正 → “时间/保持型冲突可能受益”；两者正 → “至少两种外部冲突形态方向
支持”。任何组合都保留效应量、CI、Holm p 和不匹配假设。

## 7. 制品、门禁与偏离

原始运行与 calibration 共 620 次 pipeline 样本执行（不等同精确 Ollama HTTP 调用），
API 成本 0。回传目录为 `diagnostics/boundary_v1`；`reports/boundary_matrix.md` 展示假设
预测与实际。`experiments.evidence_boundary verify` 必须从 prediction 独立重算 4 个正式
run 的 600 条 score、两基准 paired 结果、Holm、5 条假设和全部 SHA，并验证模型 digest、
配置、干净提交、`publication_gold=false`、`human_iaa=false`、`test_accessed=false`。

注册后、首个正式 prediction 前的必要修正走 `deviation:` 提交并更新活动指纹；首个正式
prediction 后禁止偏离。一次注册、一次运行、无第三基准、无 Round 2。
