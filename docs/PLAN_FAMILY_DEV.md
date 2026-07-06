# FAR 跨家族 typed/untyped dev 复现预注册（WS2）

- 状态：**注册版 v1（2026-07-06）**；由
  `experiments.protocol_family_dev.FAMILY_DEV_ACTIVE_SHA256` 校验。
- 上位路线：`docs/PLAN_LONGTERM_OPTIMIZATION.md`，活动 SHA-256
  `91eb3205fe127271bc5f4882025243d9974a711e311ef074fcbde09aa86e7cf7`。
- 本预注册不重开 RAMDocs G-A，不延续已停止的 2+4 Phase B；它只复现 F1 的
  typed-vs-untyped dev 机制对比。

## 1. 冻结问题与主张级别

问题：Qwen dev 上 typed − untyped 的 +0.078 连续答案正确率差，是可跨模型家族复现的
方向，还是 Qwen-specific 现象？WS1 已推翻 detection-only 解释：34 个正增益样本全部
经由 changed revision，因此本研究检验的是**完整 typed control（检测 + 修订）**，不把
任何正结果归因给单一组件。

G-P 已在 `diagnostics/power_v1` 完成：3 家族 × 60 配对、目标 +0.078、不一致率 19/60
时，分层 exact McNemar 功效 0.414，家族聚类 bootstrap 正区间概率 0.595，至少 2/3
家族正方向概率 0.930。因主功效 <0.60，本研究预先降格为
`directional_reproduction`：G-F 不显著不能证明机制不存在。

## 2. 冻结输入、模型与配置

- 数据仅为 `bench/splits/dev.jsonl` 的完整 60 条；运行器创建只含该文件与 corpus 的
  dev view。禁止读取 `bench/falsirag_bench.jsonl`、`bench/splits/test_inputs.jsonl`、
  train 或 RAMDocs test。
- 机器审计标签不是人类金标、真人 IAA 或 publication gold；`machine_confirmed` 35 条与
  `machine_disputed` 25 条只做强制敏感性披露。
- 两臂固定为 `far`（typed）与 `minus_typed_conflict`（untyped）。不增加上下文基线，
  不更换指标，不设 Round 2。

| 家族 | Ollama tag | 冻结 digest | 配置 | 配置 SHA-256 |
|---|---|---|---|---|
| Mistral | `mistral:7b-instruct` | `6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf` | `experiments/configs/mistral_open.yaml` | `31035391d672883e2d6f347ca3acd937cd91f2c345e960695292be88774d4b5b` |
| Google | `gemma2:9b` | `ff02c3702f322b9e075e9568332d96c0a7028002f1a5a056e0a6784320a4db0b` | `experiments/configs/gemma_open.yaml` | `2c348c6a530b31d5154b992e9f111528b81d78541ea40b48e121e6c1511098e1` |
| Meta | `llama3.1:8b` | `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` | `experiments/configs/llama_open.yaml` | `127eff6e860dc81b1252a8d8507fe499da4b5bad1e095097686f3c696e6f4090` |

除模型 tag、cache path/namespace 外，三配置的检索、NLI、temperature、token 上限完全同构。
运行必须来自已推送的干净提交，run identity 逐臂记录提交、实现 SHA、配置 SHA 与 Ollama
digest；任何 digest 或配置不符立即停止。

## 3. 运行顺序

每家族先以固定平衡选择规则跑 5 条 calibration（两臂），仅验证结构化输出、记录耗时和
确认 checkpoint 可恢复；不得根据文本、分数或耗时修改 prompt、参数、样本或判定。随后
自动进入同一冻结提交的 60 条正式运行。calibration 不进入任何统计量，正式输出可从自身
checkpoint 续跑但不得复用其他家族/配置的 prediction 行。

顺序固定为 Mistral → Google → Meta；GPU 被其他计算任务占用时等待，不抢占。Windows
所有模型、cache、工作树与输出均放 D: 盘。正式输出目录为
`/mnt/d/FAR-outputs/family_dev_v1`，回传后发布到 `diagnostics/family_dev_v1`。

## 4. 唯一主指标与 G-F

- 唯一主指标：60 条逐样本 `answer_correctness` 的 typed − untyped 连续差；三家族合并
  均值为主效应。`answer_correctness >= 0.8` 冻结为 binary success，仅用于 McNemar。
- 分层 exact McNemar：逐家族累计 candidate-only / baseline-only 不一致对；在家族内
  条件化后卷积等价于对全部不一致对执行双侧 exact binomial，alpha=0.05。必须同时满足
  typed 合并连续差 >0 与 p<0.05 才记 `gate_f_passed=true`。
- 家族聚类 bootstrap：以完整家族（60 个配对差）为 cluster，抽取 3 个家族、可放回，
  2,000 次，seed=1729；95% percentile CI 只作区间披露，不改变 G-F。
- 方向一致性：逐家族连续差 >0 计正；至少 2/3 为正时可写“方向上跨家族一致”。
- 次级描述性指标：typed conflict F1、revision accuracy 及其逐家族差；不参与 G-F。
- `machine_confirmed` / `machine_disputed` 分层分别重算连续主效应；不参与 G-F。

## 5. 预注册解读

| 结果 | 允许表述 |
|---|---|
| G-F 通过且至少 2/3 正 | 四家族 dev 方向性机制证据；仍限定机器审计、dev、非盲测 |
| G-F 未通过但至少 2/3 正 | Qwen 显著证据 + 三家族方向性复现；因功效 0.414，不得写“未显著即无效” |
| 少于 2/3 正或合并差 <=0 | 主张收窄为 Qwen-specific；保留跨家族负结果 |

不因结果增加家族、指标、子集或第二轮；不访问 held-out；不把跨家族称为外部验证。

## 6. 完整性门禁与偏离

`experiments.evidence_family_dev verify` 必须独立重算并验证：3 家族 × 2 臂各 60 条且无
重复/错误；精确模型 digest、配置与干净提交；全部预测/score/report SHA；合并 G-F、
cluster CI、方向一致性、标签敏感性；明确记录正式 360 次与 calibration 30 次 pipeline
样本执行、`api_cost_usd=0`、`publication_gold=false`、`human_iaa=false`、
`test_accessed=false`。单个 pipeline 样本可能产生多个本地 Ollama HTTP 请求，因此不把
样本执行数误称为精确模型调用数。

注册后任何实现或配置变化必须在正式运行前以 `deviation:` 提交记录并更新活动指纹；
首个正式 prediction 行写入后不再允许偏离。一次注册、一次运行、一次冻结。
