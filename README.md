# FAR：证伪增强检索

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![许可证：MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![研究状态](https://img.shields.io/badge/status-machine--audited-orange.svg)](docs/RESEARCH_STATUS.md)
[![CI](https://github.com/xiaweiyi713/FAR/actions/workflows/ci.yml/badge.svg)](https://github.com/xiaweiyi713/FAR/actions/workflows/ci.yml)

**FAR 是面向 self-correction / reflective RAG 研究者的可复现实验床：在统一 harness 下运行、比较并诊断
检索纠错方法。**

- **给谁**：需要复现、横比或定位 self-correcting RAG 失败阶段的研究者；
- **解决什么**：把“最终答案错了”拆成可审计的主张、检索、冲突检测、动作和修订轨迹；
- **现在能做什么**：离线运行 FAR、复核冻结的 8 方法 RAMDocs 制品、执行预注册的 baseline/revision ceiling；
- **安装边界**：默认 BM25 与本地 Ollama 路径不依赖 VeraRAG；显式 `vera_*` 正式配置保持可选且失败关闭。

> [!IMPORTANT]
> 当前证据是 machine-audited/upstream-labeled dev 诊断，不是 human gold 或外部盲测。
> FAR 不主张端到端普遍优越；完整 retrieval/detection/action 因果 oracle 尚需下游 replay。
> 详细阴性结果、功效、停止规则和主张边界见 [研究状态](docs/RESEARCH_STATUS.md)。

## 5 分钟开始：零 VeraRAG、零模型调用

```bash
git clone https://github.com/xiaweiyi713/FAR.git
cd FAR
python -m pip install -e .
python examples/bm25_quickstart.py
```

最小代码：

```python
from far import EvidenceDocument, FARPipeline
from far.adapters import BM25Retriever

docs = [
    EvidenceDocument(
        "d1",
        "Exercise is associated with lower blood pressure, but the observational "
        "study does not establish causality because residual confounding remains.",
    )
]
far = FARPipeline(BM25Retriever(docs), top_k_per_query=1)
result = far.run("Does exercise cause lower blood pressure?", "Exercise causes lower blood pressure.")
print(result.revised_answer)
```

`BM25Retriever` 只使用项目已声明的 `rank-bm25` 依赖。它是未指定 retrieval backend 时的默认后端；
显式 `vera_*` 配置缺少依赖时不会静默回退。

## FAR 做什么

FAR 不只积累支持性段落，而是主动问：**什么证据能够证明当前答案是错的？** 它把可能的错误类型转化为
类型化证据需求，生成支持、反驳和边界查询，再根据冲突修订答案。

```mermaid
flowchart LR
    A["问题 + 初始答案"] --> B["主张图"]
    B --> C["类型化证据需求"]
    C --> D["支持 / 反驳 / 边界查询"]
    D --> E["BM25 或可选检索栈"]
    E --> F["类型化冲突检测"]
    F --> G["动作 + 答案修订"]
    G --> H["答案 + 证据映射 + 审计轨迹"]
```

`FARPipeline.run(question, initial_answer)` 返回：

- 经过校验的无环主张图；
- 每条主张的证据需求；
- 查询与检索轨迹；
- 主张到证据的映射和类型化冲突；
- 修订后的答案及 before/after trace。

## 项目组成

| 组件 | 用途 |
|---|---|
| `far/` | 主张、证据需求、查询、冲突检测、修订和 oracle 安全门禁 |
| `far/baselines/` | 六个透明对照方法 |
| `far/bench/` | FalsiRAG-Bench 构建、标注与校验工具；安装包内含候选数据快照 |
| `bench/` | 仓库内基准数据与外部数据导入，不再是 Python 包 |
| `far/eval/` | 指标、置信区间与配对检验 |
| `far/experiments/` | 统一运行器、8 方法 RAMDocs harness、消融和 verifier |
| `diagnostics/` | 从 GitHub Release 安装的、被 Git 忽略的冻结预测/分数/指纹证据 |
| `paper/` | TMLR 主线正文与边界附录 |

当前活动路线是 [研究重定位执行计划](docs/PLAN_REDIRECTION.md)。P0/P1 已完成：

- `prereg-oracle-v1` 冻结预注册；
- FAR baseline 精确复现 RAMDocs EM `0.3114`；
- 9 条 upstream gold/wrong 标签碰撞使全样本可达 revision ceiling 为 `341/350`；
- retrieval/detection/action 在有效下游 replay 前失败关闭，避免循环论证。

P2-B/P3 的零调用观察性 trace map 也已完成：8/8 方法中，检索到至少一篇 upstream correct document 后
“答案文本已变但仍错”的数量都高于 retrieval miss；pooled 差为 `+0.3914`，sample-cluster bootstrap
95% CI `[+0.3554, +0.4275]`。由于 6 个基线没有检测/动作 trace，这支持 post-retrieval answer-transformation
failure，不证明跨方法 detection causal gap。见 [stage trace report](reports/stage_trace_map.md)。

## 安装选项

环境要求：Python 3.10+。推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync --extra dev --extra eval
uv run python examples/bm25_quickstart.py
```

离线 FAR、BM25、基准验证和冻结制品复核不需要 API key 或 VeraRAG。

若需本地 Ollama 或实验依赖：

```bash
uv sync --extra dev --extra eval --extra experiment
```

若需显式 `vera_dense`、`vera_faiss`、`vera_hybrid`、重排序或旧供应商适配器，再安装可选 VeraRAG：

```bash
uv pip install --no-deps -e /absolute/path/to/VeraRAG
export FAR_VERA_HOME=/absolute/path/to/VeraRAG
```

作者内部数据构建也可直接传 `--source-dir`；公共运行路径不读取这些私有源目录。

## 单一命令入口

`falsirag --help` 把原有平铺脚本收敛为分组命令树：

```bash
falsirag run --help
falsirag diag attribution --help
falsirag diag trace-map verify
falsirag bench validate --data-dir bench
falsirag jury readiness --help
falsirag ops repository-maintenance --check
falsirag release solo verify diagnostics/solo_v1
```

分组为 `run / diag / bench / jury / ops / release`，另保留常用的 `suite / baselines / eval` 顶层入口。
旧 `falsirag-*` 与 `far-*` console scripts 暂时兼容，但会在 stderr 给出迁移目标。

## 运行与验证

运行离线、类别均衡的小规模诊断：

```bash
uv run falsirag suite \
  --config far/experiments/configs/offline_smoke.yaml \
  --output-dir outputs/smoke_suite \
  --limit 10 \
  --baseline vanilla_rag \
  --ablation minus_typed_conflict \
  --resamples 200
```

有限样本制品会标记为 `partial` 和 `diagnostic_only`。运行器默认拒绝访问 test；只有验证过的 one-shot
流程同时提供显式授权时才允许读取留出 operational inputs。

公开检查：

```bash
uv run falsirag bench validate
uv run falsirag release scan-secrets --json
uv run ruff check .
uv run ruff format --check .
uv run mypy far tests scripts/package_smoke.py
uv run pytest
uv build
bash scripts/check_release_packages.sh
bash scripts/solo_paper_release_check.sh
```

最后一个命令还会生成可搬运且可独立复核的
`build/solo-paper-release/far-solo-paper-release.tar.gz`，并通过二次打包逐字节比较证明确定性。
归档布局、transfer 后验证和严格非真人边界见
[Portable No-Human TMLR Release](docs/SOLO_PAPER_RELEASE.md)。

wheel 与 sdist 的隔离安装 smoke 会验证：包内基准、离线配置、命令入口，以及自足 BM25 确实可用。
生成的诊断运行不会进入安装包；其逐文件指纹、确定性归档流程和发布状态见
[制品存储说明](docs/ARTIFACT_STORAGE.md)。

## 冻结研究证据

无需调用模型即可复核主要公开证据：

```bash
uv run falsirag ops diagnostic-data install
uv run falsirag release solo verify diagnostics/solo_v1
uv run falsirag ops project-status --verify
uv run falsirag release solo-paper-readiness
uv run falsirag diag fever-binary verify \
  --data-dir bench/external/fever_pair_candidates_v1 \
  diagnostics/fever_binary_v1
```

`diagnostics/` 不再由 Git 跟踪。安装器从 `artifacts-v1` release 下载 5.6 MiB
确定性归档，先核对归档 SHA-256，再核对 336 个文件和整树指纹，并拒绝覆盖已有目录。

这些命令成功只证明相应 machine-audited 诊断包完整、主张边界一致；不代表严格投稿、人类 IAA 或外部盲测就绪。

RAMDocs Round 1 的 8 方法 × 350 条预测位于 `diagnostics/ramdocs_v2/round1/`。Oracle P1 的实现与判据见：

- [预注册](docs/PREREG_ORACLE_ATTRIBUTION.md)
- [标签碰撞 amendment](docs/PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10.md)
- [P5 注册消融运行手册](docs/P5_EXECUTION.md)
- [P6 类型可映射性与可选未来人工分支](docs/P6_EXECUTION.md)
- [P6-M 机器本体稳定性运行手册](docs/P6M_EXECUTION.md)
- [P6-M 机器本体稳定性报告](reports/type_mappability_machine/type_mappability_machine.md)
- [重定位剩余外部动作顺序](docs/REDIRECTION_EXTERNAL_ACTIONS.md)
- [完整研究状态](docs/RESEARCH_STATUS.md)
- [8 方法 stage trace map](reports/stage_trace_map.md)

当前接受的无真人重定位 profile 已由 P6-M 阴性结果闭环。原 P6 人工复核/仲裁分支保持
`ready_to_analyze=false`，但已退出活动待办；它只在未来有真实人员且明确恢复严格人工主张时重新开启。
P6-M 不被称为真人复核、IAA、仲裁或金标。

## 基准与发布边界

FalsiRAG-Bench v0.2.0-candidate 有 300 条五类均衡样本和 175 篇语料文档；合并三类查询后的词法
counter-evidence recall@10 为 `0.91`。这是语料构造检查，不是 FAR 性能结果。

在真人独立复核、仲裁与外部盲测完成前，`bench/manifest.json` 保持
`publication_ready: false`。数据来源、许可与限制见 [基准数据卡](bench/CARD.md)。

## 文档导航

- [研究状态与主张边界](docs/RESEARCH_STATUS.md)
- [重定位执行路线](docs/PLAN_REDIRECTION.md)
- [系统架构](docs/ARCHITECTURE.md)
- [复现指南](docs/REPRODUCING.md)
- [评测定义](docs/EVALUATION.md)
- [真人标注协议](docs/HUMAN_ANNOTATION_PROTOCOL.md)
- [盲测交接](docs/BLIND_TEST_HANDOFF.md)
- [完成度审计](docs/COMPLETION_AUDIT.md)
- [开发日志](docs/DEVELOPMENT_LOG.md)
- [论文状态](paper/STATUS.md)

## 许可证

FAR 代码与受控合成摘要采用 [MIT License](LICENSE)。可选 VeraRAG 适配器复用 MIT 许可代码；上游数据集
和来源材料保留各自条款。FEVER 候选切片随附文件记录其 CC-BY-SA-3.0 与 GPL-3.0 来源信息。
