# 2+4 执行规划：外部上游标签验证 + 跨家族 LLM 陪审团标注

> 目标：在**零标注预算**约束下，把 FAR 从 relaxed machine-audited profile
> 推进到可投 CCF-A 主会的证据形态。
> 方案 2 = 在已有上游答案与文档标签的外部冲突基准上验证完整 FAR；
> 方案 4 = 用跨家族 LLM 陪审团 + 作者盲态仲裁替代双人独立标注。
>
> 本文一经提交即视为预注册协议。执行开始后，只允许在留出集评测**之前**、
> 并以新 commit 显式记录的方式修改；任何修改必须写入偏离日志（见 §7）。

### 2026-07-04 注册后澄清（留出集评测前）

外部源核查后，将本文中的“外部真人金标”严格解释为**外部上游标签证据**，
而不是一套独立双人复标的 publication-grade human gold。RAMDocs 的有效答案
继承自 AmbigDocs，但其误导文档由实体替换构造、噪声文档由检索采样；因此
G-A 只能证明在独立发布且带上游标签的冲突基准上的迁移，不能替代真人 IAA。

RAMDocs 论文定义了 strict exact match 判据，但公开仓库没有独立评分 CLI。
本项目据论文 §5.1 将指标冻结为：Unicode/大小写/冠词/标点/空白规范化后，
预测必须覆盖每一个 `gold_answers`，且不得包含任一 `wrong_answers`；实现同时
报告 gold coverage 与 wrong-answer exclusion，并用手工边界样例测试。该定义
在任何 RAMDocs dev/test 评分前冻结。

---

## 0. 总原则与家族隔离矩阵

**核心防御逻辑**：LLM 标注最大的审稿质疑是"作者调到自己赢为止"。对策是
(a) 预注册全部协议与判据；(b) 陪审团与被评测系统零家族重叠；
(c) 外部上游标签基准提供独立交叉验证；(d) 留出集一次性评测。

**家族隔离矩阵（冻结，不得调整）**：

| 角色 | 模型 | 家族 | 来源 | 成本 |
|---|---|---|---|---|
| 被评测系统（主） | Qwen3.5 9B | Qwen | 本地 Ollama（已有） | 0 |
| 被评测系统（矩阵） | Mistral 7B Instruct | Mistral | 本地 Ollama | 0 |
| 被评测系统（矩阵） | Gemma 2/3 9B Instruct | Google | 本地 Ollama | 0 |
| 陪审员 J1 | DeepSeek V4-Flash | DeepSeek | API（已有适配器） | 约 ¥10–30 |
| 陪审员 J2 | GLM-4-Flash 或同级 | 智谱 | API（已有适配器，免费/低价档） | ≈0 |
| 陪审员 J3 | Llama 3.1 8B Instruct | Meta | 本地 Ollama | 0 |
| 仲裁者 | 作者本人（盲态协议，§4.4） | — | — | 时间 |

陪审团（DeepSeek / 智谱 / Meta）与系统（Qwen / Mistral / Google）无家族交集。
若任一模型不可用，替换必须保持零重叠并记录偏离。

**预注册成功判据（先于任何实验冻结）**：

- **G-A（外部验证门）**：RAMDocs dev 划分上，FAR 主指标相对最强基线的
  配对 bootstrap 95% CI 下界 > 0，或 McNemar p < 0.05。
- **G-K（陪审团可用门）**：三陪审员两两 Cohen's κ 均 ≥ 0.50 且
  Fleiss κ ≥ 0.45（五种冲突类型 + `no_conflict` 的六分类）。不达标则
  降级为二分类冲突标签重算；
  二分类仍不达标则宣告陪审团路径失败。
- **G-S（自一致门）**：作者仲裁二遍重标（间隔 ≥ 14 天，20% 重抽样）
  自一致率 ≥ 0.80。
- **停止规则**：G-A 未通过 → 不进入 Phase B 的复评与投稿包装，
  转入错误分析（§6 风险 R1）。

---

## 1. Phase 0 — 预注册与数据核查（约 3 天）

1. 提交本文档；把本文 SHA-256 写入后续所有陪审团/外部评测报告的
   `protocol_fingerprint` 字段（扩展 `experiments/` 现有指纹机制）。
2. 外部数据核查：
   - RAMDocs：<https://github.com/HanNight/RAMDocs> /
     HF `HanNight/RAMDocs`（arXiv:2504.13079，MADAM-RAG 论文）。
     核对许可证、条数、字段结构，钉死 HF revision SHA。
   - WikiContradict（次选补充集）：HF
     `ibm-research/Wikipedia_contradict_benchmark`，253 条真人标注
     （NeurIPS 2024 D&B）。核对许可证（预期 CC 系）。
   - 两者的许可证文件按 `bench/external/fever_pair_candidates_v1`
     的先例落盘。
3. 拉取并烟囱测试 Mistral 7B、Gemma 9B、Llama 3.1 8B 的 Ollama 镜像
   （复用 Windows GPU 主机门禁脚本）。
4. 冻结陪审员 prompt（复用 `falsirag-auto-annotate` 的现有预标注
   prompt，仅参数化模型端点），temperature=0，结构化输出 + 现有
   重试/回退记录机制。

**产物**：本文档 + `docs/DEVELOPMENT_LOG.md` 预注册条目 + 三个本地模型
smoke 记录。

---

## 2. Phase A — RAMDocs 外部上游标签验证（约 2 周，先行）

> 先跑 Phase A 的原因：它便宜、快、决定性强。FEVER 检测器迁移已是
> null 结果；若完整 FAR 在 RAMDocs 上也不赢基线，应先修方法而不是
> 继续攒标注证据。

### A1 数据导入（2–3 天）

- 新增 `bench/external/ramdocs_v1/`，结构对齐
  `fever_pair_candidates_v1` 先例：`manifest.json`（含 HF revision、
  逐文件指纹）、语料、许可证、数据卡。
- 新 CLI：`falsirag-build-ramdocs`（对应 `verarag-build-fever-pairs`
  的模式），从钉死的 revision 确定性重建。
- 自行切分 dev/test（建议 70/30，按问题分组、种子固定、写入
  manifest）。**test 从导入之日起冻结**，复用现有 `--allow-test`
  拒绝机制。

### A2 任务映射（2–3 天）

RAMDocs 每条 = 问题 + 多文档（含歧义多答案 / 错误信息 / 噪声，
支持度不均衡）。映射协议：

- **初始答案**：与 FalsiRAG-Bench 相同协议，用 vanilla RAG 在该条
  的封闭语料上生成——保证 FAR 与基线输入对齐。
- **语料**：仅该条自带文档（closed corpus，与 CRAG-style 复现的
  封闭语料设定一致）。
- **主指标**：RAMDocs 官方口径——歧义题须覆盖全部有效答案、
  排除错误信息答案的 exact match。实现进 `eval/`，带单元测试对拍
  官方样例。
- **辅指标**：unsupported sentence rate（透明的词汇代理：逐句与该题
  `correct` 文档做规范化 token F1，最大值低于 0.50 记 unsupported）；
  "错误信息文档存在时是否报告冲突"的二分类检出率
  （RAMDocs 的 misinformation 标记提供弱真值）。
  typed conflict F1 **不可用**（无类型标签），论文中如实说明。
- 边界条件预案：若单条文档过少使 boundary 查询退化，允许按预注册
  预案缩减查询预算，偏离写入日志（§7）。

### A3 dev 实验（3–5 天，含跑批）

在 RAMDocs dev 上运行：FAR、全部 6 基线（重点 CRAG-style 与
CounterRefine-style）、typed-vs-untyped 消融。主模型 Qwen3.5 9B。
复用 `falsirag-suite` + `eval/` 的配对 bootstrap 与 McNemar。

### A4 冻结与判定（1 天）

- 结果按 `diagnostics/solo_v1` 模式冻结为 `diagnostics/ramdocs_v1`，
  `falsirag-solo-release verify` 可校验。
- **执行 G-A 判定**：
  - 通过 → 进入 Phase B，并把 RAMDocs test 留到 §5 一次性评测。
  - 未通过 → 停止规则生效：做错误分析，方法迭代只许用 dev；
    修完后 dev 上重跑记为新一轮（轮数与改动全部留痕）；
    连续两轮仍失败则论文降级（§6 R1）。

### A5 补充集（可选，2–3 天）

WikiContradict 253 条按同一适配器模式导入，仅跑 FAR + 最强两基线，
作为第二张外部表。优先级低于 Phase B，时间紧则砍。

---

## 3. Phase B — 陪审团金标与多模型矩阵（约 4–5 周，含 14 天仲裁间隔）

### B1 陪审团标注工具（3–4 天）

- 新 CLI：`falsirag-jury-annotate`，扩展现有
  `auto_annotate` / `machine_consensus` 代码路径：同一冻结 prompt
  分发到 J1/J2/J3 三端点，逐陪审员独立输出文件 + 指纹 +
  回退率记录。
- 新 CLI：`falsirag-jury-consensus`：多数票聚合；两两 Cohen's κ、
  Fleiss κ；样本分层为 `unanimous / majority / disputed`；
  报告含 `protocol_fingerprint`。
- 测试：κ 计算对拍已有 `eval/` 实现；篡改/缺文件 fail-closed。

### B2 跑标注（2–3 天）

300 条 × 3 陪审员。预算：DeepSeek 约 ¥10–30，GLM 免费/低价档，
Llama 本地。**执行 G-K 判定**；不达标走二分类降级预案。

### B3 作者盲态仲裁（1 周工作量 + 14 天间隔）

仅对 `disputed` 层（无多数票，或多数票与构造标签冲突的样本）：

1. 复用 `annotate_packet` 盲标基建：隐藏陪审员投票、隐藏系统输出、
   隐藏构造标签来源、随机打乱顺序。
2. 第一遍全量仲裁 → 冻结。
3. ≥ 14 天后，对 20% 重抽样做第二遍 → **执行 G-S 判定**。
4. 产出 `bench/labels_jury_v1/`：manifest 标记
   `label_provenance: cross_family_llm_jury_plus_author_blind_adjudication`，
   新增独立等级 `jury_gold: true`；`publication_gold` 保持 `false`
   （该字段永远留给真人 IAA，不得挪用）。

### B4 复评与敏感性（3–4 天）

- 已冻结的 11 组方法预测**无需重跑模型**，仅对 jury gold 重算分数。
- 主表：jury gold。敏感性附表：构造标签 vs jury gold vs
  unanimous-only 三口径，延续现有 confirmed/disputed 分析框架。
- 若 typed-vs-untyped 增益在 jury gold 上翻转 → 如实报告，
  论文主张回退到 relaxed profile 口径。

### B5 多模型矩阵（1 周，与 B3 间隔期并行）

- Mistral 7B 与 Gemma 9B 上跑：FAR、typed/untyped 消融、
  CRAG-style、CounterRefine-style（省时起见非全基线；全 6 基线
  仅主模型有）。
- 结构化输出回退率 > 30% 的模型按预案剔除并披露（§6 R3）。
- 产出三模型 typed-vs-untyped 增益表——这是"机制而非单模型巧合"
  的关键证据。

---

## 4. Phase 5 — 留出集一次性评测（1–2 天）

全部分析冻结、论文表格框架写完**之后**，一次性运行：

- FalsiRAG-Bench test（58 条，jury gold 口径）；
- RAMDocs test（§A1 冻结的划分）。

复用现有 one-shot 评分器与指纹链：评测前提交"预测将被评测"的
manifest，评测后立即冻结，不允许任何回改。没有外部保管人，
论文如实披露：**以冻结指纹与提交历史作为防篡改证据，而非外部盲测**。

---

## 5. Phase C — 论文与投稿（约 2 周）

### 主张重写

主张升级为（相对 relaxed profile）：

> 在跨家族 LLM 陪审团标注（预注册协议、κ 报告、作者盲态仲裁、
> 多口径敏感性分析）的 FalsiRAG-Bench 上，typed conflict control
> 相对匹配的 untyped 消融在三个开源模型家族上一致改进；
> 并在已有上游答案与文档标签的外部冲突基准 RAMDocs 上验证了端到端优势。

强制披露（沿用现有 gate 机制，新增 `falsirag-jury-paper-readiness`）：

- 标签为 LLM 陪审团 + 作者仲裁，非真人 IAA；
- refutation/boundary 消融无正向增益、typed revision 的取舍；
- FEVER 二分类迁移 null 结果；
- 无外部保管盲测，防篡改依赖指纹链；
- 系统为 7–9B 开源模型，未验证前沿闭源模型。

### 投稿目标

| 目标 | 截稿（须核实） | 评估 |
|---|---|---|
| AAAI-27 | 约 2026-08 | 时间不够（仲裁间隔 14 天已卡死），放弃 |
| ARR 2026-10 轮 → ACL/NAACL 2027 | 2026-10 中 | **主目标**，节奏合适 |
| IJCAI-27 | 约 2027-01 | 备选/改投 |
| arXiv（relaxed profile） | 立即 | 先挂占坑，兼作招募展示品 |

### 总时间线（单人、兼职强度）

```text
第 1 周      Phase 0 预注册 + 数据核查
第 2–3 周    Phase A：RAMDocs 导入、映射、dev 实验、G-A 判定
第 4 周      B1–B2：陪审团工具 + 跑标注 + G-K 判定；仲裁第一遍
第 5–6 周    14 天间隔（并行 B5 多模型矩阵、A5 可选补充集、论文初稿）
第 7 周      仲裁第二遍 + G-S；B4 复评与敏感性
第 8 周      留出集一次性评测；表格定稿
第 9–10 周   论文成稿、gate 全绿、内部检查表
→ 2026-09 中旬完成，从容赶 ARR 十月轮
```

**总预算**：API ≤ ¥50；作者时间约 60–100 小时。

---

## 6. 风险与预案

| # | 风险 | 预案 |
|---|---|---|
| R1 | RAMDocs 上 FAR 不显著（G-A 失败） | 停止规则：不进入投稿包装。错误分析 → 只用 dev 迭代方法（留痕）→ 两轮仍失败则论文转向"typed conflict control 的适用边界分析"投 findings/workshop，或回炉方法 |
| R2 | 陪审团 κ < 0.50（G-K 失败） | 降级二分类冲突标签重算；仍失败则放弃 jury gold，论文停留 relaxed profile + RAMDocs 外部表 |
| R3 | 小模型跑不动 FAR 结构化输出 | 现有确定性回退协议兜底；回退率 > 30% 剔除该模型并披露；矩阵最少保 Qwen + 1 |
| R4 | 陪审员训练数据污染（见过相关事实） | prompt 限定"仅依据给定证据判断"，不做开放事实核查；论文披露此局限 |
| R5 | 仲裁自一致 < 0.80（G-S 失败） | 争议样本整层从主表剔除，只报 unanimous+majority 口径 |
| R6 | RAMDocs 许可证不允许再分发 | 只分发重建脚本 + 指纹（FEVER 先例已有此模式） |
| R7 | jury gold 上 typed 增益消失 | 如实报告，回退 relaxed 主张；这本身是标签敏感性的诚实发现 |

## 7. 偏离日志规则

任何对本协议的修改：只允许发生在受影响评测运行之前；必须单独
commit，标题前缀 `deviation:`；同步追加到 `docs/DEVELOPMENT_LOG.md`
并说明理由。留出集评测后不允许任何偏离。

## 8. 明确不做的声明（论文红线）

- 不声称真人 inter-annotator agreement 或真人仲裁；
- 不声称外部保管盲测；
- 不声称 publication-grade human gold；
- 不声称每个 FAR 组件都有正向边际贡献；
- 不声称前沿闭源模型或跨领域的普适性。

## 9. 新增制品清单

| 制品 | 类型 |
|---|---|
| `docs/PLAN_2PLUS4.md` | 本预注册协议 |
| `falsirag-build-ramdocs` | CLI + `bench/external/ramdocs_v1/` |
| RAMDocs 官方口径指标 | `eval/` 扩展 + 对拍测试 |
| `falsirag-jury-annotate` / `falsirag-jury-consensus` | CLI + 测试 |
| `bench/labels_jury_v1/` | jury gold 标签层（`jury_gold: true`） |
| `diagnostics/ramdocs_v1/`、`diagnostics/jury_v1/` | 冻结证据包 |
| `falsirag-jury-paper-readiness` | 新论文档位 gate |
| 三模型 typed-vs-untyped 增益表 | 论文主表素材 |
