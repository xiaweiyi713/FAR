# FAR 项目企划：Falsification-Augmented Retrieval

> **Ask What Could Be Wrong: Falsification-Guided Retrieval for Self-Correcting Language Agents**
> 目标会议：**AAAI-27 主会**（按你给的 deadline：摘要 2026-07-21 / 全文 2026-07-28 / 补充 2026-07-31，主文 ≤7 页）
> 本文是 FAR 的完整项目企划：研究问题 / 方法 / 目录结构 / 技术栈 / 基准 / 实验 / 时间线 / **VeraRAG 复用映射（精确到文件）** / 风险对冲。

---

## 0. 一句话定位（决定能否中 AAAI 的唯一变量）

**不是"让 RAG 检索更多支持证据"，而是把"主动寻找能推翻自身答案的证据"做成一个由「类型化证据冲突」驱动的通用控制机制。**

> **核心机制（论文的真贡献）**：*Typed evidence conflict as a control signal that drives counterfactual (falsifying) retrieval and typed answer revision.*

这条定位同时满足两点：① 是"新问题 + 通用方法"，不是窄应用 SOTA（AAAI 友好）；② 它的骨架在 VeraRAG 里已有约 60–70%，4–5 周可冲刺。

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
DeepSeek（主）+ 1 个闭源（GPT-4o-mini/Qwen-Plus）+ 1 个开源（Qwen-open，本地）。Embedding：BGE/E5；检索：BM25+dense hybrid +可选 rerank。

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

## 9. 项目规划（5 周倒排到 AAAI-27 全文 2026-07-28）

> ⚠️ **现实提醒**：单人 4–5 周做"新基准 + 新方法 + 多模型多基线 + 7 页论文"是**极限冲刺**；VeraRAG 的高复用是它从"不可能"变"可冲刺"的唯一原因。长杆是 **FalsiRAG-Bench 构造与人工标注**。每周设 Go/No-Go，做不动就降级目标（见 §11）。

| 周 | 目标 | 产出 / Go-No-Go |
|---|---|---|
| **W1** | 立项收敛 + 脚手架 + 基准 v0 | `far/` 跑通 4 步 demo（复用 VeraRAG）；FalsiRAG-Bench **100 题**(每类 20) 含 counter_evidence；**关口：FAR 在 demo 上确实能找到反证并修正** |
| **W2** | 基准扩到 300–400 + 留盲 split + 小规模双标注 | 基准冻结+指纹；IAA κ；**关口：反证可检索率达标，否则改造语料** |
| **W3** | 主实验：FAR vs 基线 ×（2–3 模型），带 CI | 主表 v1；**关口：FAR 是否显著优于 vanilla/reflective** |
| **W4** | 消融（typed/refutation/boundary）+ case study + 人工校验 | **关口：typed > untyped 是否显著**（不显著则论文要重写卖点） |
| **W5** | 写作 + 图表 + 复现包 + 内部预审 | 7 页初稿 + 补充材料；找人模拟审稿 |

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
| **时间不够（4–5 周）** | 高 | 最大化复用 VeraRAG；基准砍到 300、模型砍到 2–3；W1/W2 设硬关口；**降级方案见下** |
| **新意被质疑（vs CRAG/CoVe）** | 高 | 主打 typed-conflict-as-control-signal + 基准 + typed 消融；Related 逐一区分 |
| **typed 消融不显著** | 高 | 若 typed 无增益→论文卖点垮；W4 早验，不行就转写成"分型诊断/负结果"或延期 |
| **反证检索不到** | 中高 | 基准语料**强制植入可检索反证**；报反证召回率 |
| **自建基准自指/tuning-to-test** | 中 | 留盲 test + 至少 1 个外部 slice（可借 FEVER pair 改造） |
| **官方 Self-RAG/CRAG 难复现** | 中 | 用诚实近似并标注，或减少基线数量、用更强的 vanilla/multi-query |

**降级方案（做不动 AAAI-27 时）**：
- 退 **EMNLP-26（~5–6 月 deadline）** 或 **AAAI-27 后续/其它 A 会**；
- 或先投 **workshop**（TrustNLP/KnowledgeNLP/RAG）占坑，再扩成主会；
- 或回到 VeraRAG 的 **NeurIPS D&B** 路线（`VeraRAG/docs/PUBLICATION_PLAN.md`）——FAR 与之共享基准/基建，不浪费。

---

## 12. 立即开始（W1 第一步）

1. `pip install -e /Users/xuwenyao/VeraRAG`，在 `far/adapters/` 薄封装 LLM/检索/冲突。
2. 写 `far/counterfactual.py` 的 **support/refutation/boundary** 三类 typed query 生成器（方法核心，优先）。
3. `bench/build/extend_from_verabench.py`：从 VeraBench 抽 temporal/conflict/misleading/numerical 题，加 `counter_evidence`/`expected_revision` 两字段，先做 **100 题 demo 集**。
4. 跑 FAR vs Vanilla 的 10 题 smoke，确认"能找到反证→正确修正"这条主链路通——**这是整个项目的 Go/No-Go**。

> 一句话收尾：**FAR 的成败不在工程量（VeraRAG 已给你 70%），而在两点——(1) typed counterfactual query 真能检索到反证并带来可测增益；(2) typed 消融显著。把 W1–W4 的关口卡死，跑出这两点，就是一篇像样的 AAAI 投稿。**
