# FAR 重定位主文档：研究主张 · 企划 · 工程实现（已采纳路线）

> 一份把**研究方向**、**落地企划**、**具体工程实现**、**开源化**四条线合到一起的执行手册。
> 目标：把项目已积累的罕见方法论严谨度，从"一个严谨但没成功的方法（FAR 端到端无优势）"迁移到
> "一个有正向骨架、单作者可完成、命题活得过自己消融的研究 + 一个别人能装能用的诊断工具"。
> 既有的预注册 / 停止规则 / 零模型调用重分析传统**全部保留**。
>
> **导航**：§0 核心主张 → §1 研究企划 → §2 工程实现（含代码骨架）→ §3 开源化 → §4 统一执行顺序。
> 只想知道"先干什么"，直接跳 §4。

---

# Part 0 · 核心研究主张（Central Thesis）

## 0.1 一句话主张

> **在自我纠错检索中，决定成败的不是"能不能发现答案与证据的冲突"，而是"发现冲突后能不能把答案改对"。
> 检测早已够用，修订才是被系统性低估的真正瓶颈——因此任何主要作用在检测/冲突控制层的创新
> （包括把冲突"类型化"），都无法转化为可迁移的端到端增益。**

标题级表达：**"Detection Is Not the Bottleneck; Revision Is."**

## 0.2 三层主张结构

- **① 方法论主张（怎么才能看清失效）**：判断一个自我纠错检索系统为什么失败，必须把端到端误差分解为
  每一阶段的**能力上限缺口（oracle gap）**与**实现缺口（implementation gap）**；只看端到端指标或事后
  错误分类都不够，因为它们分不清"这一步做不到"和"这一步没做好"。
- **② 经验主张（灵魂）**：在冲突型检索任务上，**检测阶段的 oracle gap 很小（启发式已接近上限），
  而修订阶段的 implementation gap 主导了端到端误差**，且这个瓶颈跨多个方法一致。
- **③ 从属主张（FAR 作为解释性案例）**：类型化冲突控制在受控 dev 上产生一个局部、机器审计的正向信号
  （+0.078，功效 0.414），但因为它作用在检测/控制层，所以**不端到端迁移**；类型本体对真实冲突的
  **覆盖缺口**定量解释了这种不可迁移。typed revision 是**异质收益与伤害的中介**，而非一致为正的纠错阶段。

## 0.3 它在反对什么（所以非平凡）

领域隐含共识是"自我纠错的关键在于更好地知道哪里错了"——CoVe 的 verification questions、Self-RAG 的
critique token、CRAG 的 retrieval evaluator，重心都在优化"检测/判断/reflection quality"。本主张直接顶
这个共识：**在冲突任务上检测上限早已够用，领域一直在优化一个不是瓶颈的阶段；真正欠工程化的是
"据冲突生成正确答案"这一步。**

## 0.4 为什么它是科学主张而非口号

- **可证伪**：若 oracle 检测带来的端到端增益 ≫ oracle 动作带来的增益，主张即被推翻（说明检测才是瓶颈）。
  §2 的 oracle 阶梯就是为钉死这一点设计的。
- **现有证据已强指向它**：六桶归因里"检出但改错"103 > "未检出"72；34 个正向 delta 全走 changed-revision；
  去掉 typed revision 反而总体更好。这些是"瓶颈在修订"的独立证据，只是还没被统一成一条可量化曲线。

## 0.5 叙事闭环：falsification 的教训反转

FAR 出发时相信"主动证伪能自我纠错"；证据揭示的真正教训是——**证伪（发现冲突）是容易的，
难的是据证伪把答案改对。** 于是 FAR 的负结果不再是失败，而是"作用在检测/控制层没用"的**关键正向证据**；
名字 Falsification-Augmented Retrieval 可以保留，但它现在证明的是一个反直觉的边界，而不是一个更好的方法。

---

# Part 1 · 研究重定位企划

## 1.1 新研究问题与预注册假设

**主 RQ**：端到端误差在多大程度上分别归因于各阶段 oracle gap 与 implementation gap？跨方法是否存在
一致的瓶颈阶段？

| 编号 | 子问题 | 预注册假设 | 可证伪判据 | 对应既有证据 |
|---|---|---|---|---|
| RQ1 | 检测是瓶颈吗？ | H1: 检测阶段 oracle gap 大 | oracle 检测端到端增益 < 实现改进空间 ⇒ falsified | `conflict_undetected=72` |
| RQ2 | 修订是主要中介吗？ | H2: 给定 oracle 检测+动作，修订仍是最大残余且跨方法一致 | 某方法修订残差远小于均值 ⇒ 需分层 | `conflict_detected_revision_wrong=103`；去 typed revision 反更好 |
| RQ3 | typed 有独立于"激进度"的贡献吗？ | H3: 控制修订激进度后类型的独立增量≈0 | `minus_typed_revision_aggressive` 显著劣于 full ⇒ falsified | typed/untyped 消融当前混淆 |
| RQ4 | 类型本体能覆盖真实冲突吗？ | H4: 可映射率与 typed 增益正相关 | 低可映射率数据集仍有 typed 增益 ⇒ falsified | WS3 近零迁移 |
| RQ5 | claim graph 结构有独立贡献吗？ | H5: 去依赖/拓扑序（flat）不改变端到端 | flat 显著劣于 full ⇒ falsified | 从未单独消融 |

> 沿用既有纪律：假设在跑任何 oracle 干预**之前**冻结（git tag `prereg-oracle-v1`），零模型调用重分析优先。

## 1.2 正向贡献

- **C1（方法论·主贡献）**：stage-wise oracle attribution 协议 + 开源工具（方法无关）。
- **C2（实证·核心结果）**：跨 8 方法失效地图，预期主结论"检测 oracle gap 小、修订 implementation gap 主导"。
- **C3（边界）**：类型本体外部覆盖缺口定量解释迁移天花板（把 WS3 null 转成正向发现）。
- **C4（阴性·严谨披露）**：typed control 在受控条件下无可迁移端到端增益，附功效 0.414 与边界披露。

C1–C3 均不依赖 FAR 成功 ⇒ 命题活得过消融。

## 1.3 核心资产盘点

**直接复用（P0/P1 零模型调用；后续因果 oracle 需下游 replay）**：
- `diagnostics/ramdocs_v2/round1/runs/{vanilla_rag, multi_query_rag, crag_style_reproduction,
  self_rag_style_reproduction, reflective_rag, counterrefine_style_reproduction, far,
  far_minus_typed_conflict}/` —— **8 方法 × 350 条**冻结 predictions + checkpoint，每条带完整 `claim_graph`。
- `diagnostics/ramdocs_v2/round1/evaluations/*` —— 对应打分。
- `experiments/attribution.py` —— 已有 `classify_failure` / `component_attribution` /
  `correct_document_recall` / `_revision_changed` / `retrieval_stratum` / `collection_score` / `BUCKET_PRIORITY`：
  **oracle 阶梯的离散前身，直接扩展**。
- RAMDocs upstream 正确文档标签：支持 oracle retrieval，弱支持 oracle detection。

**需要新建**：`far/oracle.py`、`experiments/oracle_ladder.py`、`ablations.py` 三个新臂、`reports/failure_map.md`。

## 1.4 保留 / 降级 / 放弃

- **保留**：预注册+停止规则+功效前置+零模型重分析全套；六桶归因（升级为阶梯离散版）；8 方法制品与 verifier。
- **降级**："typed control 更好" → 被诊断对象之一；WS2/WS3 → 为失效地图/覆盖缺口提供证据；
  release/submission/jury 门禁工具 → 冻结不再投入。
- **放弃（止损）**：2+4 jury-gold 矩阵与多模型投稿包装；AAAI 严格档；任何"证明端到端普遍更优"的新尝试。

## 1.5 论文重构

**章节**：① Intro（失效不透明是共性问题→提出 oracle attribution）② 诊断协议（C1）③ 实验设置（8 方法/oracle 定义/预注册）
④ 跨方法失效地图（C2，核心）⑤ 类型本体覆盖缺口（C3）⑥ typed 边界与阴性结论（C4，含功效）⑦ 对领域的设计启示。

**claim ladder（写进 abstract、每份 report、每张图注）**：
- 强断言（oracle/金标支撑）：跨方法失效地图的阶段归因。
- 中断言（dev+功效受限）：typed 局部信号、修订中介。
- 弱断言（near-null）：外部迁移、覆盖缺口相关性。
- 明确不主张：人类金标、外部盲测、端到端普遍优越、跨模型泛化。

---

# Part 2 · 工程实现（可照着写代码）

> 下面所有代码骨架都对齐已确认的真实接口：
> `Retriever.retrieve(query, top_k=5) -> list[EvidenceDocument]`；
> `TextGenerator.complete(prompt, *, system_prompt, temperature, max_tokens, response_format) -> str`；
> `ClaimDecomposer.decompose(answer) -> ClaimGraph`；`ClaimGraph.topological_order()`；`ClaimNode.depends_on`。

## 2.1 研究方向对应的新代码

### 2.1.1 `far/oracle.py`（新建）——阶段化 oracle 算子

关键设计修正：P1 可对冻结 prediction 做 baseline 重打分，并以 gold-answer label injection 构造修订 ceiling。
但 R/D/A 只改 metadata 而不重新计算最终 `answer` 时，EM 必然不变；这种曲线会按构造把全部增益归给修订，
不能称为端到端 oracle attribution。完整定义与传播门禁见 `docs/PREREG_ORACLE_ATTRIBUTION.md`。

```python
"""Stage-wise interventions for reflective-retrieval failure attribution.

P1 只重评分 baseline 并构造 revision label-injection ceiling；R/D/A 必须等待下游 replay。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

STAGES = ("retrieval", "detection", "action", "revision")

@dataclass(frozen=True)
class OracleConfig:
    retrieval: bool = False   # P2：必须重放下游阶段，不能只改 evidence_ids
    detection: bool = False   # P2：必须重放下游阶段，且始终称 weak oracle
    action: bool = False      # P2：必须冻结规则并重放修订
    revision: bool = False    # P1：gold-answer label-injection ceiling

def apply_oracle(
    prediction: dict[str, Any],
    gold: dict[str, Any],
    task: dict[str, Any],
    cfg: OracleConfig,
) -> dict[str, Any]:
    """P1 只接受 baseline/revision；未传播到 answer 的 R/D/A 必须 fail closed。"""
    out = dict(prediction)
    if cfg.retrieval or cfg.detection or cfg.action:
        raise NotImplementedError("R/D/A require downstream answer replay")
    if cfg.revision:
        out = {**out, "answer": " ; ".join(task["gold_answers"])}
    return out

# 复用 attribution.collection_score / correct_document_recall 做重打分
```

P1 配套两级计算（也可放 oracle.py）：

```python
P1_LADDER = (
    OracleConfig(),                                             # baseline
    OracleConfig(revision=True),                               # label-injection ceiling
)

def ladder_scores(predictions, tasks) -> list[float]:
    """P1 返回 baseline 与 revision ceiling；按 sample_id 对齐并复用冻结 RAMDocs scorer。"""
    from eval.ramdocs import score_ramdocs_answer
    scores = []
    for cfg in P1_LADDER:
        correct = sum(
            score_ramdocs_answer(apply_oracle(p, task, cfg)["answer"],
                                 task["gold_answers"], task["wrong_answers"])["ramdocs_exact_match"]
            for p, task in align_by_sample_id(predictions, tasks)
        )
        scores.append(correct / len(predictions))
    return scores
```

**验收**：baseline 精确复现已知 EM/coverage/exclusion；末级达到 label-constrained attainable ceiling。
首次 P1 运行发现 9/350 条 upstream gold/wrong 标签重叠，因此全样本可达 EM 上限为 341/350，
label-feasible 341 条上应为 1.0；详见 `docs/PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10.md`。
R/D/A 在下游 replay 落地前必须拒绝执行，不能用不改答案的占位干预生成论文曲线。

### 2.1.2 `experiments/oracle_ladder.py`（新建）——编排 + 跨方法地图

```python
METHODS = (
    "vanilla_rag", "multi_query_rag", "crag_style_reproduction",
    "self_rag_style_reproduction", "reflective_rag",
    "counterrefine_style_reproduction", "far", "far_minus_typed_conflict",
)

def compute_ladder(method_dir, golds, upstream) -> dict:
    """单方法：读 predictions.jsonl → ladder_scores → {stage: score, oracle_gap, impl_gap}。"""

def cross_method_map(round1_dir) -> dict:
    """8 方法 × 5 级 → 失效地图 dict。检测 impl_gap / 修订 impl_gap 分列，供热图。"""

def build_report(result, out_dir) -> None:
    """写 reports/failure_map.md（表 + mermaid/matplotlib 热图）+ 冻结指纹。"""
```

CLI 入口（沿用现有 shim 风格，见 `far/cli.py`）：`falsirag-oracle-ladder`，或收敛后的 `falsirag diag ladder`。

### 2.1.3 `experiments/ablations.py`（改）——补 3 个干净消融臂

当前 untyped 臂被固定为保守（RETRACT/QUALIFY），typed 是激进纠正 ⇒ 混淆"类型"与"激进度"。补：

```python
from dataclasses import replace
from far.claims import ClaimGraph, ClaimDecomposer

ABLATION_NAMES = (
    "full", "minus_typed_conflict", "minus_refutation_query", "minus_boundary_query",
    "minus_typed_revision",
    "minus_typed_revision_aggressive",  # 新：untyped 但同等激进（隔离 H3）
    "minus_typed_detection_nli",        # 新：检测层换 NLI-only（隔离 H1）
    "flat_claims",                      # 新：去依赖/拓扑序（隔离 H5）
)

class AggressiveGenericRevisionEngine(TypedRevisionEngine):
    """untyped 但与 typed 同等激进：用证据主动改写，不退化为 qualify。
    与 minus_typed_revision（GenericRevisionEngine，保守 qualify）配对，
    差值 = 类型信息的独立贡献；与 full 的差 = 激进度以外的类型贡献。"""
    def revise(self, claim, conflicts, evidence):
        if not conflicts:
            return super().revise(claim, conflicts, evidence)
        # 关键：改写强度与 typed 相同，但不读 conflict_type（去掉类型信息，保留激进度）
        controlling = max(conflicts, key=lambda c: c.confidence)
        after = self._rewrite(claim.text, controlling, RevisionAction.RETRACT
                              if controlling.strength == "strong" else RevisionAction.QUALIFY_UNCERTAINTY)
        return RevisionTrace(claim_id=claim.claim_id, before=claim.text, after=after,
                             action=RevisionAction.RETRACT, conflict_types=(),
                             evidence_ids=tuple(c.evidence_id for c in conflicts),
                             rationale="Aggressive untyped repair (type-blind, same intensity).",
                             confidence=controlling.confidence)

class FlatClaimDecomposer:
    """包裹任意 decomposer，清空 depends_on，消除图结构（隔离 claim graph 的贡献）。"""
    def __init__(self, inner: ClaimDecomposer) -> None:
        self.inner = inner
    def decompose(self, answer: str) -> ClaimGraph:
        graph = self.inner.decompose(answer)
        return ClaimGraph(tuple(replace(c, depends_on=()) for c in graph.claims))

# build_ablation 里新增分支：
#   elif name == "minus_typed_revision_aggressive": revision_engine = AggressiveGenericRevisionEngine()
#   elif name == "flat_claims": decomposer = FlatClaimDecomposer(decomposer or RuleBasedClaimDecomposer())
#   elif name == "minus_typed_detection_nli": detector = NLIOnlyConflictDetector(...)  # 依赖模型，成本高
```

> `minus_typed_revision_aggressive` 与 `flat_claims` 可纯离线/轻量重跑；`minus_typed_detection_nli`
> 需要 NLI 模型（`far/adapters/conflict.py` 已有 NLI 挂点，默认关闭），归入增强层。

### 2.1.4 类型可映射性研究（`experiments/type_mappability.py` 新建，C3）

- 输入：WS3 的 WikiContradict / Google CONFLICTS 冲突样本。
- 标注协议：每条冲突标 `clean | partial | unmappable`（能否映射到 7 类之一）；LLM 预标 + 人工校验；披露 κ。
- 输出：每数据集**可映射率**，回归"可映射率 × typed−untyped delta"，产出 `reports/type_mappability.md`。

## 2.2 项目健康度与可复现改进（与开源化共用）

### 2.2.1 切断私有 VeraRAG 耦合（**开源生死线**）

现状：`far/adapters/{retrieval,conflict,llm}.py` 延迟 import `src.*`（VeraRAG），仓库外私有，外人跑不起真实后端。
你已有 `InMemoryRetriever`，且 `rank-bm25` 已在依赖里 —— 补一个自足的真实后端即可开箱可跑：

```python
# far/adapters/retrieval.py 新增（零 VeraRAG，仅用已声明的 rank-bm25）
from rank_bm25 import BM25Okapi

class BM25Retriever:
    """自足 BM25 检索后端，不依赖 VeraRAG。作为开箱默认真实后端。"""
    def __init__(self, corpus: list[EvidenceDocument]) -> None:
        self._docs = list(corpus)
        self._bm25 = BM25Okapi([d.text.split() for d in self._docs])
    def retrieve(self, query: str, top_k: int = 5) -> list[EvidenceDocument]:
        scores = self._bm25.get_scores(query.split())
        ranked = sorted(zip(self._docs, scores), key=lambda x: -x[1])[:top_k]
        return [replace(d, score=float(s)) for d, s in ranked]
```

- 把 `VeraRetrieverAdapter` / `from src.*` 全部改成**可选**：`try/except ImportError` 且给出清晰提示
  "真实 VeraRAG 后端为可选，未安装时回落 BM25Retriever"。`far` 核心 + BM25 后端必须能独立 `pip install` 跑通。
- LLM 后端同理：默认给一个基于 `ollama`/`openai`（已在 experiment extra）的 `TextGenerator`，`src.utils.llm_client` 变可选。
- 删除测试硬编码绝对路径：`tests/test_benchmark.py` 的 `/Users/xuwenyao/VeraRAG` → 环境变量 `FAR_VERA_HOME` + `skipif`。
- `bench/build/{import_fever_slice,extend_from_verabench}.py` 的 `../../../VeraRAG` → 可选 + 文档标注为"作者内部数据构建路径"。

### 2.2.2 CLI 收敛：53 平铺入口 → 一个主命令

```python
# far/cli.py 重构为 argparse 子命令树；旧 falsirag-* 保留为 deprecated alias（打印迁移提示）
falsirag run ...            # = falsirag-run
falsirag diag ladder ...    # 新：oracle 阶梯
falsirag diag attribution   # = falsirag-attribution
falsirag bench validate     # = falsirag-validate-bench
falsirag jury annotate ...  # = falsirag-jury-annotate
falsirag ops maintenance    # = falsirag-repository-maintenance
```

分组：`run / diag / bench / jury / ops / release`。新人 `falsirag --help` 一眼看全，替代当前 50+ 平铺脚本。

### 2.2.3 命名空间收拢（根治 VeraRAG 冲突）

`experiments` / `bench` / `baselines` / `eval` 作为顶层包与 VeraRAG 同名冲突，`cli.py` 的 `_prefer_far_repo()`
sys.path hack 是治标。迁移到 `far.` 命名空间：`far.experiments` / `far.bench` / `far.baselines` / `far.eval`。
改动面大（所有 import + CI + pyproject `packages.find`），排在工程线后期做，一次性消除 hack。

### 2.2.4 数据与代码分离

`diagnostics/` 约 41MB（8×350 predictions/checkpoint 等）压在 git 历史里拖慢 clone。
迁到 git-lfs 或独立 `far-artifacts` 数据分支/release，主仓只留 `reports/` 摘要与指纹。保留现有 200MB 门限校验。

---

# Part 3 · 开源化

> 判断：现状是**好的研究工件**（可复现论文、纪律严谨），但还不是**好的开源项目**——卡在定位模糊 +
> 可安装性（VeraRAG 耦合），不在代码质量。最有前途的开源形态（诊断实验床）与本研究重定位**同源**，一次投入两头受益。

## 3.1 产品定位（一句话）

> **FAR：在统一 harness 下复现并诊断 8 种自我纠错 RAG 方法的实验床，带阶段化 oracle 失效归因。**

对象：做 self-correction / reflective RAG 的研究者。解决：横比多方法、把端到端失败定位到具体阶段。

## 3.2 README 重构

- 顶部换成产品四问：**这是什么 / 给谁 / 解决什么 / 10 行 quickstart**（用 `FARPipeline` + `BM25Retriever` + `InMemoryRetriever`）。
- 诚实限定声明（machine-audited / dev / 非金标）**保留但下沉**到 `docs/RESEARCH_STATUS.md`。
- 顶部放跨方法失效地图那张图 —— 一图说清项目价值。

## 3.3 quickstart 目标（外人 5 分钟跑通，零 VeraRAG）

```python
from far.pipeline import FARPipeline
from far.adapters.retrieval import BM25Retriever
from far.models import EvidenceDocument

corpus = [EvidenceDocument(evidence_id="d1", text="...")]
far = FARPipeline(BM25Retriever(corpus))
result = far.run(question="...", initial_answer="...")
print(result.revised_answer, result.to_dict()["conflicts"])
```

## 3.4 维护责任（先想清楚再决定）

"好的开源项目"= 为外部用户背长期维护成本（issue / 兼容 / 使用姿势）。**先选定位**：
- 只当**论文可复现附件** → 现状已够格，别背包袱，Part 3 可跳过；
- 要一个**被别人用和引用的诊断工具** → 走 §3.1 定位，值得，且与论文同源。

---

# Part 4 · 统一执行顺序（研究 + 工程 + 开源合并排期）

> 原则：先做**零模型调用、纯复用冻结制品**的高杠杆动作（既出论文核心结果，又验证工程管道），
> 再做需要重跑/标注的增强，最后做大改面的命名空间/开源化。MVP 全程不碰新模型调用。

| 阶段 | 动作 | 线 | 依赖 | 产物 | MVP |
|---|---|---|---|---|---|
| **P0** | 预注册 `docs/PREREG_ORACLE_ATTRIBUTION.md`（RQ1–5/H1–5/oracle 四算子定义/判据），`git tag prereg-oracle-v1`；旧战线归档 | 研究 | — | 冻结预注册 | ✅ |
| **P1** | `far/oracle.py` + 单测：实现 baseline + revision label-injection ceiling；验证 baseline=已知 EM、全体 ceiling=341/350、label-feasible ceiling=1.0 | 工程 | P0 | 评分对齐、标签碰撞审计与修订 ceiling | ✅ |
| **P2** | 选择并冻结：A) R/D/A 下游 replay（需要模型调用），或 B) 零调用 trace attribution（不得称 oracle gap）；弱金标冲突 + ~50 条人工校验披露 κ | 工程 | P1 | 有效传播的阶梯或观察性失效图 | ✅ |
| **P3** | `experiments/oracle_ladder.py`：8 方法跨方法失效地图 + 热图 + verifier + 指纹 | 工程 | P2 | `reports/failure_map.md`（C2） | ✅ |
| **P4** | 论文重写 MVP 版（C1 协议 + C2 地图 + C4 阴性），claim ladder 对齐 | 研究 | P3 | TMLR 稿 | ✅ |
| P5 | `ablations.py` 三新臂；`minus_typed_revision_aggressive` + `flat_claims` 轻量重跑 | 研究 | P3 | H3/H5 结论 | 增强 |
| P6 | 类型可映射性标注 + 回归（C3） | 研究 | P3 | `reports/type_mappability.md` | 增强 |
| P7 | 切断 VeraRAG（BM25/LLM 自足后端）+ 删硬编码路径 + quickstart | 开源 | — | 开箱可跑 | 开源必做 |
| P8 | README 产品化重构 + `docs/RESEARCH_STATUS.md` 下沉 | 开源 | P7 | 产品化 README | 开源必做 |
| P9 | CLI 收敛（子命令树 + deprecated alias） | 开源 | P7 | 单主命令 | 开源建议 |
| P10 | 命名空间收拢（`far.*`）+ 数据/代码分离（lfs/release） | 工程 | P9 | 消除 hack、轻 clone | 开源建议 |

**关键路径（出论文核心结果）**：P0 → P1 为零模型调用；P2 若选择真正因果 oracle，R/D/A 必须重放下游并产生新答案，
因此不能再宣称全程零模型调用。若坚持零调用，则 P2/P3 必须降格为 trace attribution，避免循环论证。
**开源线**：P7 → P8 可与研究线并行（互不阻塞），是"能不能给别人用"的生死线。
**大改面**（P10）留最后，避免中途震荡。

## 4.1 建议的第一步（本周可动手）

1. 写 `docs/PREREG_ORACLE_ATTRIBUTION.md` 并 `git tag prereg-oracle-v1`。
2. 起 `far/oracle.py` + `tests/test_oracle.py`：只做 baseline + revision label-injection ceiling 两级；
   baseline 复现证明无意外泄漏；ceiling 必须同时报告全样本可达上限、label-feasible 子集的 1.0 与标签碰撞。
3. 把本文件从"提案"提升为"已采纳路线"，`README.md` 状态表加一行"WS-D 诊断重定位（进行中）"。

## 4.2 诚实性守则（延续既有传统，不可退让）

- 任何 oracle 干预/假设，跑前 `git tag` 冻结；零模型调用重分析优先。
- `*_style_reproduction` 一律披露为"同一 harness 下的受控复现"，不冒充官方实现。
- oracle 检测用弱金标时全程标注"弱 oracle"，不写成 human gold。
- 阴性结论（C4）与功效（0.414）永远与正向结论并列，不追溯改写门禁。
- claim ladder 四档分级出现在 abstract、每份 report、每张图注。

---

## 附：一句话带走

**这个项目不再主张"我做了个更会证伪的检索器"，而是主张"整个领域把力气用错了地方——自我纠错的瓶颈在修订
不在检测，我有一套 oracle 归因协议 + 8 方法失效地图能证明它"。** 同一份重构，既让论文的正向命题活过消融，
又让代码成为一个别人能装能用的诊断工具。先从 P0 + P1 动手，两周内就能看到 oracle 阶梯是否支撑核心主张。
