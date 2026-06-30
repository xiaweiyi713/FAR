# FAR 项目企划：Falsification-Augmented Retrieval

> **Ask What Could Be Wrong: Falsification-Guided Retrieval for Self-Correcting Language Agents**
> 目标会议：**AAAI-27 主会**（[官方 CFP，2026-06-29 核验](https://aaai.org/conference/aaai/aaai-27/main-technical-track-call/)：摘要 2026-07-21 / 全文 2026-07-28 / 补充 2026-07-31；正文最多 7 页、含参考文献最多 9 页）
> 本文是 FAR 的完整项目企划：研究问题 / 方法 / 目录结构 / 技术栈 / 基准 / 实验 / 时间线 / **VeraRAG 复用映射（精确到文件）** / 风险对冲。

> **执行状态**：企划到实现的逐项证据见 [`docs/PROPOSAL_TRACEABILITY.md`](docs/PROPOSAL_TRACEABILITY.md)。代码、候选基准、运行器、统计和论文骨架已实现；独立双标注/仲裁、外部保管的盲测以及冻结的多模型结果仍是不可由机器结果替代的投稿门槛。

---

## 0. 一句话定位（决定能否中 AAAI 的唯一变量）

**不是"让 RAG 检索更多支持证据"，而是把"主动寻找能推翻自身答案的证据"做成一个由「类型化证据冲突」驱动的通用控制机制。**

> **核心机制（论文的真贡献）**：*Typed evidence conflict as a control signal that drives counterfactual (falsifying) retrieval and typed answer revision.*

这条定位同时满足两点：① 是"新问题 + 通用方法"，不是窄应用 SOTA（AAAI 友好）；② 它的骨架在 VeraRAG 里已有约 60–70%，使当前 29 天冲刺仍有执行可能。

---

## 1. 研究问题与动机

**问题**：当前 agentic RAG 的主流回路是 `query → retrieve → generate → (reflect) → answer`，几乎只检索"支持自己答案"的证据，很少主动检索"能推翻自己答案"的证据；其 self-reflection 多是 LLM 自说自话，无法定位"错在哪一类"。

**研究问题（一句话）**：
> *How can a retrieval-augmented agent actively seek **falsifying** evidence and revise its answer under **typed** evidence conflicts?*

**主张**：可靠的知识密集型推理需要的不是 evidence accumulation，而是 **falsification-driven reasoning**——把"我可能错在哪"显式转化为**可检索的证据需求**，再用**类型化冲突**决定如何修正。

---

## 2. 核心贡献（三条，缺一不可）

- **C1（新问题 + 框架 FAR）**：提出 falsification-guided RAG 任务与 FAR 框架——claim 分解 → 类型化证据需求 → 反事实查询（support/refutation/boundary）→ 类型化冲突感知修正。
- **C2（方法新意：typed conflict 作为控制信号）**：冲突不是笼统 contradiction，而是 **temporal / entity / numerical / causal / source / definition / counter** 分型，且**不同类型驱动不同的反事实查询与不同的修正动作**。**消融必须证明 "typed > untyped"**，这是论文立得住的关键。
- **C3（评测 FalsiRAG-Bench）**：一个专门隔离"证伪失败"的小而硬基准——温度变化 / 数值不一致 / 实体混淆 / 因果过度 / 多源冲突；**语料中刻意包含反证**，使"能否检索到反证"成为可测能力。

> ⚠️ **新意红线（AAAI 最大被拒理由）**："主动找反证 / 自纠错检索"已有很近的邻居（**CRAG、Chain-of-Verification、Self-RAG、RQ-RAG、self-contradiction detection**）。"找反证"本身**不够新**。你能守住的只有：**(a) typed conflict 作为控制信号；(b) FalsiRAG-Bench 隔离证伪失败；(c) typed-ablation 证明分型确有增益**。论文每一节都要往这三点上钉。

---

## 3. 方法设计：FAR 框架

### Step 1 — Claim Decomposition（答案 → 可验证 claim 图）
把初始答案拆成带依赖关系的 claim graph（事实 / 推断 / 因果 / 数值 / 时间节点）。
> 复用 VeraRAG `AnswerClaim`(claim_type/verifiable/support_type) + `ReasoningAgent`；**新增**：claim 间依赖边（graph，而非 list）。

### Step 2 — Typed Evidence Requirement & Conflict（每个 claim 需要哪类证据 + 检测分型冲突）
为每个 claim 分配"需要哪种证据类型"，再检测分型冲突。

| Evidence/Conflict Type | 作用 | 修正含义 |
|---|---|---|
| Temporal | 时间是否正确 | 修时间线 |
| Entity | 主体是否一致 | 重限定主体（母/子公司） |
| Numerical | 数值是否支持 | 换数值 + 降确定性 |
| Causal | 是否把相关写成因果 | 因果降级为相关 |
| Source-Reliability | 来源是否可靠 | 偏好权威源 |
| Definition | 指标/概念定义是否一致 | 偏好共识定义 |
| Counter-Evidence | 是否存在反例 | 强反证→推翻 / 弱→标注不确定 |

> 复用 VeraRAG `ConflictType` 的 10 个分型检测器 + `RESOLVE_*` 策略（几乎 1:1）；**新增**：claim→evidence-type 的**正向需求分配**（VeraRAG 只检测、不分配需求）。

### Step 3 — Counterfactual Query Generation（**论文方法新意主战场**）
对每个 claim 生成三类 query，而非只生成支持查询：
1. **Support Query**：找支持证据；
2. **Refutation Query**：找能反驳的证据（按 claim 类型定向：数值→找不同数值，因果→找"仅相关/第三因"，时间→找不同日期/版本）；
3. **Boundary Query**：找定义差异、时间边界、可比性条件（"不同 setting 不可比"）。
> 复用 VeraRAG `DynamicRetrievalAgent.seek_counter_evidence` + query-variant 生成作为脚手架；**这一步必须重写成"按 claim 类型系统化生成三类 typed query 的协议"**——这是 FAR 区别于"reflect+重检索"的核心，**不能只复用**。

### Step 4 — Conflict-Aware Typed Revision（按冲突类型修正）
按检测到的分型冲突执行修正：修时间线 / 换数值并降确定性 / 重限定主体 / 因果降级 / 强反证则推翻 / 无反证则保留并标注不确定。输出 = **Answer + Claim-level Evidence Map + Conflict Types + Revision Trace**（可解释、可评估）。
> 复用 VeraRAG `RepairAgent` + `RESOLVE_*` + `UncertaintyController` 决策；**新增**：显式 before→after **revision trace** 日志（评测 Revision Accuracy 用）。

---

## 4. 技术栈

| 层 | 选型 | 来源 |
|---|---|---|
| 语言/打包 | Python 3.10+，pyproject + ruff + mypy + pytest | 沿用 VeraRAG 规范 |
| LLM 后端 | DeepSeek / 通义千问 / GPT-4o(-mini) / 开源(Qwen-open via vLLM/Ollama) | **复用 VeraRAG `llm_client`（6 provider 统一接口）** |
| Embedding/检索 | BM25(rank-bm25+jieba) / BGE/E5 dense / FAISS / Hybrid(RRF) + CrossEncoder rerank | **复用 VeraRAG `retriever/`** |
| NLI/冲突 | rule detectors + CrossEncoder NLI(nli-distilroberta) | **复用 VeraRAG `conflict_graph`** |
| 统计 | bootstrap CI + McNemar 配对检验 | **复用 VeraRAG `evaluation/statistics.py`** |
| 复现 | benchmark SHA-256 指纹 / run signature / 断点续跑 | **复用 VeraRAG `run_verabench` 基建思想** |
| 论文 | LaTeX（AAAI 模板）+ matplotlib 图 | 新建 `paper/` |

---

## 5. 目录结构（FAR 新建 repo，精简、面向论文 artifact）

```
FAR/
├── README.md
├── PROJECT_PROPOSAL.md          # 本文
├── pyproject.toml / requirements.txt
├── far/                         # 核心包（FAR 方法）
│   ├── __init__.py
│   ├── claims.py                # Step1: claim 分解 + claim graph
│   ├── evidence_types.py        # Step2: 证据类型需求分配（薄层，调用 verarag 冲突检测）
│   ├── counterfactual.py        # Step3: support/refutation/boundary 查询生成 ★新核心
│   ├── revision.py              # Step4: typed 冲突感知修正 + revision trace
│   ├── pipeline.py              # FAR orchestrator（串起四步）
│   └── adapters/                # 对 VeraRAG 的薄封装（见 §6 复用方式 A）
│       ├── llm.py               #   wraps verarag LLMClient
│       ├── retrieval.py         #   wraps verarag retriever + seek_counter
│       └── conflict.py          #   wraps verarag ConflictGraphBuilder/ConflictType
├── bench/                       # FalsiRAG-Bench
│   ├── falsirag_bench.jsonl     # 主数据（含 counter_evidence/expected_revision）
│   ├── corpus.jsonl             # 含反证的语料（关键：反证必须在库内）
│   ├── schema.py                # 样本/校验 schema
│   ├── build/                   # 构造脚本（从 VeraBench 扩展+重标）
│   │   ├── extend_from_verabench.py
│   │   ├── add_counter_evidence.py
│   │   ├── annotate_packet.py   # 双标注 packet（改自 verarag 双盲协议）
│   │   └── validate_bench.py    # 结构/指纹/留盲校验
│   └── CARD.md                  # datasheet（构造/来源/license/局限）
├── baselines/                   # 对照系统
│   ├── vanilla_rag.py           # 复用 verarag baseline
│   ├── multi_query_rag.py       # 新（基于 query-variant）
│   ├── self_rag.py / crag.py    # 复用/复现
│   └── reflective_rag.py        # iterative-retrieval reflect baseline
├── eval/
│   ├── metrics.py               # 复用 verarag answer/evidence/conflict metrics + 新增 2 指标
│   ├── stats.py                 # 复用 verarag statistics（bootstrap/McNemar）
│   └── run_eval.py              # 评测 runner（带 split/指纹/CI）
├── experiments/
│   ├── run_far.py               # 跑 FAR + 各消融
│   ├── run_baselines.py
│   └── configs/                 # 模型/检索/消融 yaml
├── tests/                       # 单测（claims/counterfactual/revision/metrics）
├── paper/                       # AAAI LaTeX + 图 + abstract
└── outputs/                     # 结果(gitignored)
```

---

## 6. VeraRAG 复用映射（核心问题：哪些能复用、怎么复用）

**复用方式**（二选一，建议 A）：
- **方式 A（推荐，干净）**：把 VeraRAG 作为本地依赖：`pip install -e /Users/xuwenyao/VeraRAG`，在 `far/adapters/` 里 `from verarag ...` / `from src ...` 薄封装调用。FAR 只写 FAR 特有层。优点：不背 VeraRAG 整个工程化包袱，论文 artifact 干净。
- **方式 B（vendoring）**：把需要的少数模块复制进 `far/_vendor/`。优点：FAR 自包含、可单独发布；缺点：要手动同步。

> 建议：**先用 A 快速跑通，临投稿前若要独立 artifact，再 vendor 关键 4 个文件。**

### 逐文件复用表

| FAR 需要 | VeraRAG 现成文件 | 复用度 | 怎么用 / 要改什么 |
|---|---|---|---|
| Claim schema | `src/utils/data_structures.py`（`AnswerClaim`/`Claim`/`ConflictType`/`VeraRAGOutput`） | 🟢🟢 | 直接 import；**新增** claim graph 的依赖边字段 |
| Claim 分解 | `src/agents/reasoning_agent.py`（生成 answer_claims） | 🟢 | 复用其 claim 抽取 prompt；改成"对**已生成答案**做分解"（FAR 是 answer→claims） |
| **类型化冲突** | `src/evidence/conflict_graph.py`（10 检测器 + `ConflictType` + `RESOLVE_*`） | 🟢🟢 **最大复用** | 直接复用分型检测与 `RESOLVE_*` 决策表；**新增** claim→证据类型**需求分配** |
| 反证检索脚手架 | `src/agents/retrieval_agent.py`（`seek_counter_evidence` + query variants） | 🟡 | 复用接口；**Step3 三类 typed query 协议要重写**（方法新意） |
| 冲突感知修正 | `src/agents/repair_agent.py` + `UncertaintyController` | 🟢🟢 | 复用降级/标注/拒答/推翻逻辑；**新增** revision trace 日志 |
| 检索器 | `src/retriever/`（BM25/Dense/FAISS/Hybrid/rerank） | 🟢🟢 | 直接复用 |
| LLM 客户端 | `src/utils/llm_client.py`（6 provider） | 🟢🟢 | 直接复用 |
| 评测指标 | `src/benchmark/evaluator.py` + `src/evaluation/*`（Conflict-F1/Unsupported-Claim-Rate/Evidence P-R/Citation） | 🟢🟢 | 复用；**新增** Revision Accuracy、Overclaim Reduction |
| 统计严谨 | `src/evaluation/statistics.py`（bootstrap CI / McNemar） | 🟢🟢 | 直接复用 |
| 基线 | `experiments/baselines/`（vanilla/hybrid/self_rag/long_context） | 🟢 | vanilla/long_context 直接用；self_rag 需升级为正版或诚实标注；**新增** CRAG / multi-query |
| 基准胚胎 | `data/verabench/`（temporal/conflict/misleading/numerical/unanswerable） | 🟢🟢 | **FalsiRAG-Bench 从它扩/重标**，别从零造（见 §7） |
| 构造/校验/双盲标注/指纹/污染审计 | VeraRAG `experiments/validate_*` + 双盲 pair 协议 + 迁移脚本 | 🟢 | 改造复用到 FalsiRAG-Bench |

**一句话**：FAR ≈ VeraRAG 的（claim schema + 分型冲突 + 修正引擎 + 检索 + 评测 + 统计 + 基线 + 基准胚胎）**复用**，外加你**新写的 Step3 typed counterfactual query 协议 + 基准两字段 + 两指标**。新写量约占全项目 30%，且恰好是论文贡献所在。

---

## 7. FalsiRAG-Bench 设计

**从 VeraBench 扩展，不要从零造。** 在 VeraBench 样本 schema 上**加两个字段**并按 5 类重标：

```json
{
  "id": "F001",
  "category": "causal_overclaim",         // temporal_shift | numerical_conflict | entity_confusion | causal_overclaim | multi_source_conflict
  "question": "...",
  "initial_answer": "...",                  // 一个会犯错的初始答案（可由弱模型/构造生成）
  "claims": [ {"claim":"...", "type":"causal", "depends_on":[...]} ],
  "gold_evidence": [ {"id":"E1","text_span":"...","type":"causal"} ],
  "counter_evidence": [ {"id":"C1","text_span":"...","refutes_claim":2,"conflict_type":"causal"} ],  // ★新
  "conflict_type": "causal",
  "expected_revision": {"action":"downgrade_causal_to_correlation","revised_answer":"..."}            // ★新
}
```

**关键设计约束（决定方法能否展示价值）**：
- **语料中必须真实包含 counter_evidence**——否则 FAR 的反事实查询"找不到反证"，方法无从体现。`bench/corpus.jsonl` 要为每个 falsifiable claim 植入可检索的反证文档。
- 5 类各 ~60–80 题，**总 300–400**；其中固定 **留盲 test split**（方法/prompt 只在 train+dev 调）。
- 小规模**双人标注 + 报 IAA(Cohen's κ)**（至少在 conflict_type 和 expected_revision 上）。
- 来源：Wikipedia/Wikidata、arXiv/leaderboard 元数据、公开报告——**动态网页须存快照保证可复现**。可部分复用你已有的 VeraBench 语料与金融/论文项目样本。

---

## 8. 实验设计

### 模型（2–3 个就够，证明不绑单模型）
冻结后的主矩阵使用 DeepSeek V4-Flash（主）+ Qwen3.7 Plus 2026-05-26（闭源快照）+ Qwen 3.5 9B（开放权重、本地）。Embedding：固定版本 BGE；检索：BM25+dense hybrid + CrossEncoder rerank。滚动 API 别名不用于正式结果。

### 基线（横向）
1. Naive/Vanilla RAG ·2. Multi-query RAG ·3. Self-RAG/Reflective ·4. CRAG ·5. Iterative agentic RAG。

### 消融（纵向，**证明 FAR 各部件有用**——审稿人最看重）
- FAR − typed conflict（退化成 untyped contradiction）→ 证明 **C2 typed 有用**
- FAR − refutation query（只 support）→ 证明**反事实检索有用**
- FAR − boundary query
- FAR − revision trace / typed revision（改成笼统 repair）

### 指标（别只看 answer accuracy）
| 指标 | 含义 | 来源 |
|---|---|---|
| Answer Correctness | 最终答案对否 | 复用 |
| Unsupported Claim Rate | 无证据支持 claim 占比 | 复用 |
| Conflict Detection F1 | 是否检出分型冲突 | 复用 |
| **Revision Accuracy** | 发现冲突后是否正确修正 | **新（需 expected_revision）** |
| **Overclaim Reduction** | 因果/数值夸大下降 | **新** |
| Evidence Precision | 引用证据是否真支持 | 复用 |

全部带 **bootstrap CI + McNemar 配对检验**（复用）。**留盲 test 报告主结果**；加 case study + 小规模人工校验。

### 预期结果结构（论文里这样呈现，数值待跑）
> *FAR improves typed conflict detection F1 by 15–25 points, reduces unsupported/overclaimed statements by 20–35%, and improves revision accuracy especially on temporal and causal-overclaim tasks, over vanilla / multi-query / reflective baselines; ablations show **typed** conflict and **refutation** queries each contribute.*

---

## 9. 项目规划（自 2026-06-29 起四周倒排到 AAAI-27 全文）

> ⚠️ **现实提醒**：从 2026-06-29 到正文截止只有 29 天。工程脚手架和 300 条候选集已经完成，剩余长杆是**独立标注、冻结的多模型实验、typed 消融和外部盲测**。每周设 Go/No-Go；未通过就收缩论文主张，而不是用诊断结果补表。

| 日期 | 目标 | 产出 / Go-No-Go |
|---|---|---|
| **06-29--07-05** | 冻结开发协议 + 启动标注 | 完成形式栈 dev 诊断；生成非金标机器预标注与 Label Studio 包；两位标注者开始独立复核；**关口：反证召回和数据校验继续达标** |
| **07-06--07-12** | 冻结 gold/dev + 多模型主实验 | 完成仲裁和 IAA；跑 DeepSeek V4-Flash、Qwen3.7 Plus、Qwen3.5 9B 的 FAR 与主要基线；**关口：FAR 是否优于 vanilla/reflective** |
| **07-13--07-20** | 四项消融 + 统计 + 论文主表 | 完成 paired CI/McNemar、类别分析和 case study；**关口：typed > untyped 是否成立；不成立则在摘要前改写为诊断/负结果** |
| **07-21--07-28** | 摘要提交 + 外部盲测 + 正文收口 | 07-21 前冻结标题/摘要；外部保管人一次性跑 test；填正式表图，完成人工政策审查和模拟审稿；07-28 交正文 |
| **07-29--07-31** | 补充材料与代码归档 | 复现包、SBOM/指纹、最终 checklist、补充材料和代码归档；07-31 提交 |

> 摘要 07-21 前必须有主表雏形；07-28 交全文；07-31 交补充/代码。

---

## 10. 论文骨架（AAAI 7 页）

1. Intro：RAG 只累积支持证据 → 漏掉 falsification → FAR + 一个隔离证伪失败的基准。
2. Related：RAG/agentic RAG、self-correction(CRAG/CoVe/Self-RAG)、contradiction/NLI、selective prediction——**逐一点明缺口，明确 FAR 的差异 = typed conflict 控制信号**。
3. Method：FAR 四步（重点 Step3 typed counterfactual query + Step2/4 typed conflict→revision）。
4. FalsiRAG-Bench：5 类、含反证语料、留盲、IAA（精简 datasheet）。
5. Experiments：主表（FAR vs 5 基线 × 模型，带 CI）+ **消融表（typed/refutation/boundary）** + 指标。
6. Analysis：分型增益来自哪、失败案例、何时无效。
7. Limitations & Conclusion：诚实写局限（规模、检索上限、自建基准）。

**必备图表**：① 主对比表（带 CI/McNemar）；② **消融表（典型化是否有用）—— 论文命门**；③ 按冲突类型的增益分解图；④ revision trace 案例图；⑤ 反证检索召回率（证明方法机制真起作用）。

---

## 11. 风险与对冲

| 风险 | 严重度 | 对冲 |
|---|---|---|
| **时间不够（29 天）** | 高 | 最大化复用 VeraRAG；基准固定 300、模型固定 3 个；每周设硬关口；**降级方案见下** |
| **新意被质疑（vs CRAG/CoVe）** | 高 | 主打 typed-conflict-as-control-signal + 基准 + typed 消融；Related 逐一区分 |
| **typed 消融不显著** | 高 | 07-20 前完成；若 typed 无增益，转写成"分型诊断/负结果"或延期，不接触 test 调参 |
| **反证检索不到** | 中高 | 基准语料**强制植入可检索反证**；报反证召回率 |
| **自建基准自指/tuning-to-test** | 中 | 留盲 test + 至少 1 个外部 slice（可借 FEVER pair 改造） |
| **官方 Self-RAG/CRAG 难复现** | 中 | 用诚实近似并标注，或减少基线数量、用更强的 vanilla/multi-query |

**降级方案（做不动 AAAI-27 时）**：
- 不用不完整标注或本地 test 冒充正式证据；保留完整 artifact，转投后续主会周期（届时重新核验官方 deadline）；
- 或先投仍开放且主题匹配的 workshop（提交前核验征稿与双投政策），再扩成主会；
- 或回到 VeraRAG 的 **NeurIPS D&B** 路线（`VeraRAG/docs/PUBLICATION_PLAN.md`）——FAR 与之共享基准/基建，不浪费。

---

## 12. 当前执行入口

1. **已完成**形式检索/冲突栈的 60 条 CPU dev 诊断并冻结 top-k、模型版本和失败分析；结果仅用于开发，不填投稿主表。
2. **已完成**本地 Qwen2.5 的 300/300 非金标预标注与 Label Studio 预测包（重试后仅 1 条保守 fallback）；另已生成 300/300 规则弱标注和机器一致性审计，标出 127 条优先人工复核样本。这些产物明确为 `publication_gold: false`，只能用于提速复核，不能替代双人标注。曾在对话中暴露的 API key 不写入仓库，必须轮换后才可用于云模型。
3. **外部待办**：两位标注者独立完成盲包、仲裁并冻结 benchmark；机器建议只用于提速，不能计作独立人工标签或 Cohen's κ。
4. **进行中**：本地 Qwen3.5 9B 已通过 D:-backed、关闭思考、按样本卸载的真实管线验收；原始 60 条 dev 主方法已无错误完成并被门禁标为非投稿诊断结果。实体类 dev 失败分析已修复两个独立缺口：LLM claim 缺少确定性 typed 属性/允许新增词汇，以及运行器丢弃语料公开实体元数据；后者新增的高精度 fallback 在 train+dev 隔离审计中为 20/48 实体、0/194 非实体误报。另已修复 untyped 包装器逐文档检测、未保持 FAR 批量冲突图的消融公平性缺口；旧 untyped 队列在 44/60 停止并完整保留，提交 `96e32b7` 的修正版 FAR + 5 基线 + 4 消融全套已在 Windows GPU 上从零重跑。首次 corrected-suite 尝试因远端 Ollama/tmux 停止而在首条样本前后退出且未产生 checkpoint，已保留事故目录；当前已用 D:-backed Ollama runtime 重启新 suite，并以 `/mnt/d/FAR-outputs/latest_far_corrected_suite_path.txt` 记录最新输出路径；其中 corrected FAR 主方法已完成 60/60、零错误，预测 SHA 为 `992a4cf027db5491feef2a57210d8a9395be61798c0ff84b29760d495bc96b56`，消融和基线仍在继续。隔离审计、事故目录和旧队列均不作为论文结果；DeepSeek V4-Flash 与 Qwen3.7 Plus 仍需轮换后的云凭据。
5. **已完成盲测交接技术演练**：从当前 machine-seeded benchmark 生成并审计了 58 条 test、175 篇净化语料的 gold-free dry-run bundle；包内仅含三份允许文件，test 严格五字段，未发现 gold、expected revision、反证角色、依赖组、构造元数据或冲突/修订标签字段，文件指纹已记录在 `docs/BLIND_TEST_HANDOFF.md`。这只关闭技术路径，不关闭真实盲测：只有 dev 比较、四项消融、代码、配置、人工 gold 和主张全部冻结后，才从 adjudicated 数据重建新包并交给外部保管人一次性执行；机器种子或本地 test 绝不升级为投稿证据。

> 一句话收尾：**FAR 的成败不在工程量（VeraRAG 已给你 70%），而在两点——(1) typed counterfactual query 真能检索到反证并带来可测增益；(2) typed 消融显著。把 W1–W4 的关口卡死，跑出这两点，就是一篇像样的 AAAI 投稿。**
