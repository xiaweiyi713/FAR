# 2+4 执行手册与当前状态

权威协议为 [`PLAN_2PLUS4.md`](PLAN_2PLUS4.md)。本文件只记录可执行命令和
当前进度，不修改成功判据。活动协议指纹由
`experiments/protocol_2plus4.py` 强制校验。

## 当前状态（2026-07-05）

| 阶段 | 状态 | 权威证据 |
|---|---|---|
| 预注册 | 完成 | 原始提交 `84bbbfd`；所有澄清均为独立 `deviation:` 提交 |
| RAMDocs 导入 | 完成 | 500 题、2766 文档、MIT、HF revision `9c041b…`；350/150 已冻结 |
| RAMDocs dev | 证据完成 | 8 方法 × 350 条、8 份报告和 7 组配对比较均完整；正式 verifier `valid=true`；冻结于 `diagnostics/ramdocs_v1/dev` |
| G-A | **失败，停止规则已触发** | FAR 与最强 `multi_query_rag` 均为 0.3114；差 0；95% CI [-0.0286, 0.0314]；McNemar p=1.0 |
| G-K 陪审团 | 工具完成、禁止执行 | G-A 未通过；没有陪审团输出或 jury gold |
| G-S 作者复标 | 工具完成、禁止执行 | Phase B 未启动；不存在作者仲裁制品 |
| 多模型矩阵 | 工具完成、禁止执行 | G-A 停止规则阻断 jury-gold 矩阵与投稿主张 |
| 一次性 test | 工具完成、禁止执行 | dev 停止规则已触发，RAMDocs/FalsiRAG test 均未访问 |
| Round 2 dev 方法迭代 | 运行中 | FAR-only 第二轮已在原 detached 工作树 `d8d5f40` 恢复；恢复后 checkpoint 已从 105/350 推进到至少 231/350，Ollama、RAMDocs runner 和 llama-server 均 active |
| 2+4 论文门 | 失败关闭 | 当前首轮 2+4 路线不可进入投稿包装；只有 Round 2 完成且 G-A 通过才可改判 |

## RAMDocs

```bash
uv run falsirag-build-ramdocs verify \
  --output-dir bench/external/ramdocs_v1
```

## Phase 0 本地模型 smoke

Mistral、Gemma 与 Llama 的本地 smoke 只使用固定短提示，不读取任何 benchmark。
Round 2 已终止并完成 finalize/verify、正式工作树允许切到最新 `main`、Windows GPU
空闲且 D: 至少有 20 GiB 可用后执行：

```bash
ssh windows-gpu
cd /mnt/d/FAR-workspace/FAR-2plus4
git checkout --detach origin/main
scripts/smoke_2plus4_models.sh --pull
falsirag-verify-2plus4-smoke \
  --output-dir /mnt/d/FAR-outputs/model_smoke_2plus4
```

脚本发现 RAMDocs 服务或其他 GPU 任务时以状态 75 退出等待；模型与输出均位于 D:，
不会写入 C:。正式记录写到 `/mnt/d/FAR-outputs/model_smoke_2plus4/{mistral,google,meta}.json`，
每份都绑定活动协议、Ollama 模型摘要与 digest，并固定
`benchmark_data_accessed=false`、`human_iaa=false`。脚本结束前会自动调用同一
verifier；独立命令可在之后重新核对精确三文件集合、当前配置 SHA-256、协议指纹、
模型家族/名称/digest 和来源声明。不带 `--pull` 时只检查现有模型，不下载缺失镜像。

正式 Windows GPU 运行或 checkpoint 恢复使用 D: 盘脚本；它会启动 D: 盘
Ollama、继承 D: 盘 HuggingFace cache，并复用同一个输出目录续跑。长任务由
systemd 用户服务直接持有，不依赖 SSH 创建的 tmux pane scope。启动器会
fail-closed 检查 systemd linger；Windows 登录保活任务应使用
`scripts/keep-wsl-training-online.ps1`：

```bash
mkdir -p ~/.config/systemd/user
cp scripts/systemd/far-ollama-2plus4.service ~/.config/systemd/user/
cp scripts/systemd/far-ramdocs-phase-a.service ~/.config/systemd/user/
cp scripts/systemd/far-ramdocs-round2.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

Phase A 首轮完整 suite 使用：

```bash
ssh windows-gpu
cd /mnt/d/FAR-workspace/FAR-2plus4
scripts/start_windows_ramdocs_suite.sh
```

Round 2 FAR-only dev 方法迭代使用：

```bash
ssh windows-gpu
cd /mnt/d/FAR-workspace/FAR-2plus4
scripts/start_windows_ramdocs_round2.sh
```

`start_windows_ramdocs_round2.sh` 只在 GPU 空闲时启动 `far-ollama-2plus4.service`
与 `far-ramdocs-round2.service`。若显存或利用率显示其他任务正在占用 GPU，它只
写入 `/mnt/d/FAR-runtime/ramdocs_dev_v2.keep-running` 与
`ramdocs_dev_v2.waiting-for-gpu`，然后退出；Windows watchdog 会在 GPU 空闲后
恢复同一 checkpoint。若输出目录已有 `run_identity.json`，该脚本会拒绝用不同
Git commit 或 dirty 工作树续跑，以避免 checkpoint 签名不一致。

当前已经启动的 105/350 Round 2 checkpoint 绑定在远端 detached 工作树
`d8d5f40`。恢复这一次未完成 checkpoint 前，**不要**为了使用新脚本而 checkout
到最新 `main`，也不要把新脚本复制到 detached 工作树造成 dirty 状态。GPU 空闲时
应让 Windows watchdog 自动恢复，或在保持原 detached 工作树不变的情况下直接启动
既有 systemd units：

```bash
rm -f /mnt/d/FAR-runtime/ramdocs_dev_v2.waiting-for-gpu
systemctl --user start far-ollama-2plus4.service
systemctl --user start far-ramdocs-round2.service
```

查看状态与日志：

```bash
systemctl --user status far-ollama-2plus4.service far-ramdocs-phase-a.service far-ramdocs-round2.service
journalctl --user -fu far-ramdocs-phase-a.service
journalctl --user -fu far-ramdocs-round2.service
```

Round 2 专用只读健康检查：

```bash
scripts/check_windows_ramdocs_round2.sh
```

该脚本不会启动、停止或修改任何服务；它同时显示服务状态、checkpoint 行数与
最新样本、GPU 使用、相关进程、Ollama `n_decoded` 尾部和 run log 错误。若
checkpoint 暂时不增长但 `llama-server` 仍在运行、GPU 满载且 `n_decoded` 继续
增加，应视为慢样本正在生成，不要重启或中断。

`scripts/systemd/far-tmux-server.service` 只用于其他交互式 tmux 工作；正式
RAMDocs 进程不再依赖 tmux。

启动器会创建 D: 盘授权 marker
`/mnt/d/FAR-runtime/ramdocs_dev_v1.keep-running`。Windows 保活任务只在该
marker 存在且 `suite_manifest.json` 尚未生成时恢复被意外 stop/disable 的
两个正式服务。若 FAR 尚未占用 GPU，watchdog 会先检查显存与利用率；检测到
其他任务时等待，GPU 空闲才启动。suite 完成后自动删除 marker。若需人工
中止，必须先删除 marker，再停止服务：

```bash
rm -f /mnt/d/FAR-runtime/ramdocs_dev_v1.keep-running
systemctl --user disable --now far-ramdocs-phase-a.service far-ollama-2plus4.service
```

Round 2 使用独立 marker `/mnt/d/FAR-runtime/ramdocs_dev_v2.keep-running` 和
等待标记 `/mnt/d/FAR-runtime/ramdocs_dev_v2.waiting-for-gpu`；若需人工中止
Round 2，必须先删除 marker，再停止服务：

```bash
rm -f /mnt/d/FAR-runtime/ramdocs_dev_v2.keep-running /mnt/d/FAR-runtime/ramdocs_dev_v2.waiting-for-gpu
systemctl --user disable --now far-ramdocs-round2.service far-ollama-2plus4.service
```

运行器只向模型加载当前题目的文档。`test_inputs.jsonl` 只有
`id/question/split`；未给 `--allow-test` 时 test 会被拒绝。

## G-A 结果与停止规则

正式证据包位于 [`diagnostics/ramdocs_v1/dev`](../diagnostics/ramdocs_v1/dev)，
可复现错误分析位于
[`diagnostics/ramdocs_v1/error_analysis`](../diagnostics/ramdocs_v1/error_analysis)。

- FAR 与最强基线 `multi_query_rag` 的 strict exact match 均为 109/350
  （0.3114）。
- 配对结果：共同正确 93、FAR-only 16、baseline-only 16、共同错误 225。
- 配对差 0；bootstrap 95% CI [-0.0286, 0.0314]；McNemar p=1.0。
- FAR 的 gold coverage 略高（0.7510 vs 0.7457），但 wrong-answer exclusion
  略低（0.5686 vs 0.5743），二者在 strict exact match 上抵消。
- G-A 为 false，故 Phase B、jury gold、多模型矩阵和一次性 test 均未启动。

Round 2 只改变 FAR 的最终答案合并层；初始答案和最强基线沿用 Round 1 的冻结
制品并逐文件校验 SHA-256。FAR 350 条完成后执行：

截至 2026-07-06 08:01 +08:00，远端 Round 2 FAR 已在原 detached 工作树
`d8d5f40` 恢复并确认推进。恢复时 checkpoint 为 105/350；随后写入到至少
231/350，最后观测样本为 `RAM0330`。尚无 `run_manifest.json` 或
`predictions.jsonl`；`far-ollama-2plus4.service`、`far-ramdocs-round2.service`
和 `llama-server` 均 active。恢复前曾因 GPU 被 VeraRAG/SelfRAG 占用而保留
`/mnt/d/FAR-runtime/ramdocs_dev_v2.waiting-for-gpu`；恢复时未切换工作树。

```bash
uv run python -m experiments.ramdocs_round2 finalize \
  --data-dir bench/external/ramdocs_v1 \
  --round1-dir /mnt/d/FAR-outputs/ramdocs_dev_v1 \
  --round2-dir /mnt/d/FAR-outputs/ramdocs_dev_v2 \
  --config experiments/configs/ramdocs_qwen_round2.yaml
uv run python -m experiments.ramdocs_round2 verify \
  --data-dir bench/external/ramdocs_v1 \
  --round1-dir /mnt/d/FAR-outputs/ramdocs_dev_v1 \
  --round2-dir /mnt/d/FAR-outputs/ramdocs_dev_v2 \
  --config experiments/configs/ramdocs_qwen_round2.yaml
```

只有 `round_manifest.json` 与 verifier 同时给出 `gate_a_passed=true` 才可进入
Phase B；再次失败则按预注册规则降级论文，且仍不得访问 test。

若第二轮失败，生成冻结的跨轮错误分析：

```bash
uv run python -m experiments.ramdocs_round2_error_analysis \
  --data-dir bench/external/ramdocs_v1 \
  --round1-dir /mnt/d/FAR-outputs/ramdocs_dev_v1 \
  --round2-dir /mnt/d/FAR-outputs/ramdocs_dev_v2 \
  --config experiments/configs/ramdocs_qwen_round2.yaml \
  --output-dir /mnt/d/FAR-outputs/ramdocs_dev_v2/error_analysis
```

该入口要求 Round 2 verifier 有效且 G-A 明确失败；否则拒绝生成“失败分析”。

Round 2 判定和（若失败）错误分析完成后，冻结完整跨轮证据包：

```bash
uv run falsirag-2plus4-release build-ramdocs-round2 \
  --data-dir bench/external/ramdocs_v1 \
  --round1-dir /mnt/d/FAR-outputs/ramdocs_dev_v1 \
  --round2-dir /mnt/d/FAR-outputs/ramdocs_dev_v2 \
  --config experiments/configs/ramdocs_qwen_round2.yaml \
  --output-dir /mnt/d/FAR-outputs/diagnostics/ramdocs_v2
uv run falsirag-2plus4-release verify-ramdocs-round2 \
  --data-dir bench/external/ramdocs_v1 \
  --bundle-dir /mnt/d/FAR-outputs/diagnostics/ramdocs_v2
```

该 bundle 内嵌完整 Round 1、Round 2、配置和逐文件指纹；无论 G-A 通过或失败
都可冻结，但必须保持 `test_accessed=false`、`human_iaa=false`。若 G-A 失败，
builder/verifier 还会强制重算 `round2/error_analysis` 的配对结果、discordant 样本
和来源指纹，并要求 `paper_downgrade_required=true`；缺少或漂移时拒绝发布。

第二轮失败后，更新 `paper/main.tex` 与 `paper/STATUS.md`，再执行失败分支论文门：

```bash
uv run falsirag-round2-failure-readiness \
  --data-dir bench/external/ramdocs_v1 \
  --bundle-dir diagnostics/ramdocs_v2 \
  --output reports/ramdocs_round2_failure_readiness.json
```

该门重新验证完整 release，并要求论文明确写出第二轮 G-A 失败、两轮停止规则、
typed-conflict control applicability-boundary analysis、Phase B/held-out 未运行、
upstream-label 与非真人 IAA 来源边界。它不允许把“诚实停止”误报成 2+4 正结果。

重建 dev 错误分析：

```bash
uv run python -m experiments.ramdocs_error_analysis \
  --data-dir bench/external/ramdocs_v1 \
  --suite-dir diagnostics/ramdocs_v1/dev \
  --output-dir diagnostics/ramdocs_v1/error_analysis
```

## 陪审团

> 当前首轮禁止执行以下命令：G-A 已失败。它们只保留为未来经过新一轮
> dev 方法修订并重新通过 G-A 后的实现入口。

三个 juror 必须使用同一 packet 和冻结 prompt：

```bash
gate_args=(
  --ramdocs-data-dir bench/external/ramdocs_v1
  --ramdocs-round1-dir diagnostics/ramdocs_v2/round1
  --ramdocs-round2-dir diagnostics/ramdocs_v2/round2
  --ramdocs-config diagnostics/ramdocs_v2/round2/config.yaml
)

uv run falsirag-jury-annotate --packet-dir outputs/annotations/falsirag_packet_v1 \
  --config experiments/configs/jury_deepseek.yaml --juror-id J1 \
  --model-family deepseek --output-dir outputs/jury/deepseek "${gate_args[@]}"

uv run falsirag-jury-annotate --packet-dir outputs/annotations/falsirag_packet_v1 \
  --config experiments/configs/jury_glm.yaml --juror-id J2 \
  --model-family glm --output-dir outputs/jury/glm "${gate_args[@]}"

uv run falsirag-jury-annotate --packet-dir outputs/annotations/falsirag_packet_v1 \
  --config experiments/configs/jury_llama.yaml --juror-id J3 \
  --model-family meta --output-dir outputs/jury/meta "${gate_args[@]}"

# 三份运行分别完成后逐一独立验真
uv run falsirag-jury-annotate --verify \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --config experiments/configs/jury_deepseek.yaml --juror-id J1 \
  --model-family deepseek --output-dir outputs/jury/deepseek "${gate_args[@]}"
uv run falsirag-jury-annotate --verify \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --config experiments/configs/jury_glm.yaml --juror-id J2 \
  --model-family glm --output-dir outputs/jury/glm "${gate_args[@]}"
uv run falsirag-jury-annotate --verify \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --config experiments/configs/jury_llama.yaml --juror-id J3 \
  --model-family meta --output-dir outputs/jury/meta "${gate_args[@]}"
```

不得使用此前粘贴到聊天中的 DeepSeek key；它应视为已泄露。正式 J1 运行只接受
轮换后通过 `DEEPSEEK_API_KEY` 环境变量注入的密钥，任何 key 都不得写入仓库。
`gate_args` 指向已经 build/verify 的完整 Round 2 release；annotator 会重新执行
Round 2 verifier，只有 `gate_a_passed=true`、`phase_b_authorized=true` 且停止规则关闭
才会初始化模型或写输出。三份 juror manifest 均绑定同一个 G-A manifest SHA-256。

```bash
uv run falsirag-jury-consensus --data-dir bench \
  --juror-dir outputs/jury/deepseek --juror-dir outputs/jury/glm \
  --juror-dir outputs/jury/meta --output-dir outputs/jury/consensus \
  "${gate_args[@]}"

uv run falsirag-jury-consensus --verify --data-dir bench \
  --juror-dir outputs/jury/deepseek --juror-dir outputs/jury/glm \
  --juror-dir outputs/jury/meta --output-dir outputs/jury/consensus \
  "${gate_args[@]}"
```

## 作者盲态仲裁

```bash
uv run falsirag-jury-adjudication build-round1 \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --consensus-dir outputs/jury/consensus \
  --output-dir outputs/jury/author_adjudication

# 你本人只填写 round1_packet.jsonl 内的 author_annotation，然后立即冻结
uv run falsirag-jury-adjudication freeze-round1 \
  --output-dir outputs/jury/author_adjudication \
  --completed-file outputs/jury/author_adjudication/round1_packet.jsonl

# round1_freeze.json 记录的 eligible_at 至少 14 天后才允许创建第二遍盲包
uv run falsirag-jury-adjudication build-round2 \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --consensus-dir outputs/jury/consensus \
  --output-dir outputs/jury/author_adjudication

# 你本人只填写 round2_packet.jsonl 内的 author_annotation，然后冻结并计算 G-S
uv run falsirag-jury-adjudication freeze-round2 \
  --output-dir outputs/jury/author_adjudication \
  --completed-file outputs/jury/author_adjudication/round2_packet.jsonl

# 仅 G-K 与 G-S 均通过后编译最终 jury labels
uv run falsirag-jury-adjudication compile \
  --consensus-dir outputs/jury/consensus \
  --adjudication-dir outputs/jury/author_adjudication \
  --juror-dir outputs/jury/deepseek \
  --juror-dir outputs/jury/glm \
  --juror-dir outputs/jury/meta \
  --output-dir bench/labels_jury_v1
```

只编辑 packet 的 `author_annotation`。两轮都必须由作者本人在看不到 jury 投票、
构造标签和系统输出的条件下完成；Codex、其他 LLM 或自动脚本不能代填并冒充作者。
第一遍冻结后，`build-round2` 会核验时间戳；不足 14 天直接失败。G-S 通过后使用
`compile` 生成 `bench/labels_jury_v1`，并固定 `jury_gold: true`、
`publication_gold: false`、`human_iaa: false`。

## 多模型与留出集

Mistral/Gemma 使用 `experiments/configs/mistral_open.yaml` 和
`experiments/configs/gemma_open.yaml`。每个家族只跑 FAR、untyped、CRAG-style、
CounterRefine-style；可用 `scripts/run_2plus4_model_family.sh` 启动固定方法集。
`falsirag-jury-rescore` 用 jury labels 重算，
`falsirag-model-matrix` 汇总三家族方向与回退率。

该启动脚本在调用任何模型前会运行 `experiments.phase_b_gate`，默认验证
`diagnostics/ramdocs_v2/{round1,round2}`；路径不同时只能通过
`RAMDOCS_DATA_DIR`、`RAMDOCS_ROUND1_DIR`、`RAMDOCS_ROUND2_DIR` 和
`RAMDOCS_ROUND2_CONFIG` 显式覆盖。G-A 未通过时脚本立即失败，不产生矩阵预测。

主模型 Qwen 还必须运行 `falsirag-jury-sensitivity`，对已冻结的 11 种方法同时
报告构造标签、完整 jury gold 和 unanimous-only 三种口径；该报告是最终
readiness 的硬要求。

正式 jury evidence release 必须携带三份 juror 原始输出、作者两轮仲裁、三个
系统家族的原始 dev suite 以及复评结果；只复制最终报告不足以通过 verifier：

```bash
uv run falsirag-2plus4-release build-jury \
  --data-dir bench \
  --consensus-dir outputs/jury/consensus \
  --juror-dir J1 outputs/jury/deepseek \
  --juror-dir J2 outputs/jury/glm \
  --juror-dir J3 outputs/jury/meta \
  --adjudication-dir outputs/jury/author_adjudication \
  --labels-dir bench/labels_jury_v1 \
  --sensitivity-dir diagnostics/jury_v1/qwen_sensitivity \
  --suite-dir qwen diagnostics/solo_v1/experiments \
  --suite-dir mistral outputs/model_matrix/mistral \
  --suite-dir google outputs/model_matrix/google \
  --family-dir qwen diagnostics/jury_v1/families/qwen \
  --family-dir mistral diagnostics/jury_v1/families/mistral \
  --family-dir google diagnostics/jury_v1/families/google \
  --matrix-report diagnostics/jury_v1/model_matrix.json \
  --output-dir diagnostics/jury_v1/release

uv run falsirag-2plus4-release verify-jury \
  --data-dir bench \
  --bundle-dir diagnostics/jury_v1/release
```

`verify-jury` 会从源制品重算 G-K consensus、G-S 后的完整标签、三家族 jury-gold
复评、Qwen 三口径敏感性和最终矩阵；它不是只检查文件是否存在。

test 前先用 `falsirag-one-shot prepare` 写 intent。prepare 会失败关闭地要求
G-A 通过、完整 G-K/G-S jury labels、Qwen 三口径敏感性和三家族 dev 矩阵均已
冻结；不能只凭 `--allow-test` 越过这些前置门禁。例如：

```bash
uv run falsirag-one-shot prepare \
  --target falsirag \
  --benchmark-input bench/splits/test_inputs.jsonl \
  --data-manifest bench/manifest.json \
  --method far \
  --ramdocs-gate-manifest diagnostics/ramdocs_v2/round2/round_manifest.json \
  --jury-labels-manifest bench/labels_jury_v1/manifest.json \
  --sensitivity-report diagnostics/jury_v1/qwen_sensitivity/sensitivity_report.json \
  --matrix-report diagnostics/jury_v1/model_matrix.json \
  --output diagnostics/jury_v1/falsirag_test/one_shot_intent.json
```

提交该 intent 后才运行预测；完成后用 `falsirag-one-shot seal` 同时绑定 intent
commit、evaluation commit、suite 指纹和实际评分 manifest。seal 还会核对目标、
输入指纹、方法集以及 FalsiRAG 58 条 / RAMDocs 150 条的完整评分数。该机制是本地
防篡改证据，不得称为外部保管盲测。

正式 test 推理只能通过 `falsirag-suite` / `falsirag-ramdocs-suite`，并同时传入
`--allow-test --one-shot-intent <已提交的 intent>`。底层 FAR、baseline 与 RAMDocs
runner 使用进程内授权上下文；脱离经过验证的 suite 调用时，即使单独传
`--allow-test` 也会在读取 `test_inputs.jsonl` 前失败关闭。
