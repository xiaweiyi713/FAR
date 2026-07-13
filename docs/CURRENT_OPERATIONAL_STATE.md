# FAR 当前运行状态

状态时间：2026-07-13 11:47 CST
适用范围：长期路线 WS1--WS6、重定位 P0--P10 与 P6-M；当前无 GPU 任务。

## 当前结论

- 当前接受的无真人重定位 profile 已完成：P6-M 阴性结果是终止证据；人工 P6 已从活动队列移出，
  不再等待复核者或仲裁者。只有未来主动恢复严格人工可映射性/IAA/gold 主张时才重新开启。
- P6-M 三家族双视图正式运行已完成：J1/J2/J3 均为 `434/434`，失败尝试 `0`；
  本地确定性 verifier 返回 `valid=true`、`errors=[]`。
- 机器面板稳定性低：J1/J2/J3 分别为 `50/217`、`88/217`、`24/217`；只有
  `15/217`（`0.0691`）形成共识，202 条 contested。该结果不能替代人工 P6，不能报告
  总体可映射率、human IAA/gold 或 H4 confirmation。
- `far-p6m.service` 与 `far-ollama-2plus4.service` 均为 inactive，远端无 P6-M Python、
  Ollama 或 llama-server 进程；本机从未下载或运行模型。
- 原 P6 仍为 217/217 机器预标完成、`ready_to_analyze=false`。这是被保留的非活动严格人工协议；
  没有模型结果写入人工槽位，也不影响当前无真人 profile 的完成状态。

## 既有 WS1--WS6 结论（2026-07-09 冻结）

- WS1--WS6 均已有本地可复算证据，长期路线账本返回 `valid=true` 且
  `goal_complete=true`。后续不再需要 GPU；剩余动作是可选的 commit/push、release
  packaging 与作者人工审阅，而不是路线内必需实验。
- WS2 三个 family 已全部完成并正常退出；本地 release 已 finalize，独立 verifier 返回
  `valid=true`、`errors=[]`、`gate_f_passed=true`、`direction_consistent=true`。
- WS3 外部 boundary mapping 已完成、同步回本地并 finalize。独立 verifier 返回
  `valid=true`、`errors=[]`、`gate_b_complete=true`、`global_pass_fail=null`、
  `required_claim_level=directional_boundary_mapping`、`publication_gold=false`、
  `human_iaa=false`、`test_accessed=false`。
- WS3 release 覆盖 600 条 formal pipeline predictions 与 20 条 calibration predictions：
  - WikiContradict calibration：`5/5 + 5/5`，formal：`150/150 + 150/150`；
  - Google/RAG conflicts calibration：`5/5 + 5/5`，formal：`150/150 + 150/150`；
  - 8 个 run manifest 均为 `status=complete`、`errors=0`。
- WS3 主结论不是全局胜负：WikiContradict typed-minus-untyped boundary score 为
  `+0.0033`，95% CI `[-0.0067,+0.0167]`；Google/RAG conflicts 为 `-0.0007`，
  95% CI `[-0.0271,+0.0262]`；两个 Holm-adjusted McNemar p 均为 `1.0`。
  预注册假设中 Google outdated-information 子组正向（`+0.0040`）、no-conflict 子组
  保持安全非劣（`-0.0042 >= -0.03`），Wiki explicit/implicit 预测被反驳。论文应写成
  “弱 A-line/窄边界”，不得写成外部全局 transfer 或 end-to-end superiority。
- 远端 `windows-gpu` 上 `far-boundary.service` 与 `far-ollama-boundary.service` 均已停止；
  `far-family-dev@google.service`、`far-family-dev@meta.service`、
  `far-ollama-family-dev.service`、旧 Mistral resume service 也均为 inactive。进程复核无
  `experiments.family_dev`、`experiments.boundary`、`ollama serve`、`llama-server` 或
  `train.py`；GPU compute app 为空，仅剩 `/Xwayland` 桌面基础显存占用约 600MiB。
- 今晚不再启动 GPU、Ollama、远程训练或任何 held-out/test 运行。若继续工作，只做本地
  非 test verifier、提交整理或论文人工审阅。
- 未访问 held-out/test；仍不得把 LLM jury 或机器标签称为真人 IAA。

## WS2 最终证据

- 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
- 输入目录：`/mnt/d/FAR-outputs/family_dev_input_v1`
- 当前运行 family：无（WS2 已完成）
- 当前进度：
  - Google `calibration/far`：`5/5`，complete；
  - Google `calibration/minus_typed_conflict`：`5/5`，complete；
  - Google `runs/far`：`60/60`，complete；
  - Google `runs/minus_typed_conflict`：`60/60`，complete；
  - 上述四个 Google checkpoint 均为预期行数、ID 唯一、`errors=0`；Google family
    manifest 的协议、模型、digest、config SHA、冻结 source commit 与安全标志均匹配。
  - Meta/Llama typed 校准：`5/5`、5 个 ID 唯一，complete manifest 已核验为
    `errors=0`、`partial=true`；
  - Meta/Llama untyped 校准：`5/5`、5 个 ID 唯一，complete manifest 已核验为
    `errors=0`、`partial=true`；
  - Meta/Llama 正式 `runs/far`：`60/60`、60 个 ID 唯一、无重复，complete manifest 为
    `errors=0`、`missing_ids=[]`、`partial=false`、`split=dev`，predictions SHA 为
    `9346aaedcfe3463fa0aff9aad78f60b5dd0bb22c2d6a2ce70e4e8ea93fd048bd`；
  - Meta/Llama 正式 `runs/minus_typed_conflict`：`60/60`、60 个 ID 唯一、无重复，
    complete manifest 为 `errors=0`、`missing_ids=[]`、`partial=false`，predictions SHA 为
    `b817be0fce003965c7a68957c752190d3ff1e280d603e5d71d4e50fde8477d9b`；
  - Meta calibration run identity 已复核为冻结提交 `bd575857...`、`git_dirty=false`、
    `llama3.1:8b`、预注册 digest/config SHA、`split=dev`、`limit=5`。
- 当前日志位置：
  - `journalctl --user -u far-family-dev@meta.service -n 120 --no-pager`
  - `journalctl --user -u far-ollama-family-dev.service -n 120 --no-pager`
  - `scripts/watch_windows_family_dev.sh windows-gpu`
- 已完成 family：Mistral
- `mistral / far`
  - checkpoint：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/checkpoint.jsonl`
  - 完整性：`60/60` 行、60 个 ID 唯一、无重复组
  - manifest：`status=complete`、`completed=60`、`expected=60`、`partial=false`、`errors=0`
  - predictions SHA：
    `7c72e569a05f131515e85b225c947388ceca87aafef6d00eced580ed683180b5`
- `mistral / minus_typed_conflict`
  - checkpoint：
    `/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/minus_typed_conflict/checkpoint.jsonl`
  - 完整性：`60/60` 行、60 个 ID 唯一、无重复组
  - manifest：`status=complete`、`completed=60`、`expected=60`、`partial=false`、`errors=0`
  - predictions SHA：
    `2643726e3965e86a58cb6afab0223695fc4db7c0df28a3862782c2275d802ae3`
- Mistral family manifest：
  `/mnt/d/FAR-outputs/family_dev_v1/family_manifests/mistral.json`
- 已完成 family：Mistral、Google/Gemma、Meta/Llama。
- 本地最终 release：`diagnostics/family_dev_v1`。G-F 结果为合并连续差
  `+0.0645`、三家族方向 `3/3` 为正、分层 exact McNemar `31 vs 9`、
  `p=0.000680`、家族 cluster bootstrap 95% CI `[+0.0528,+0.0735]`，G-F 通过。
- 由于 G-P 功效仍为 `0.414`，许可结论仍只是 `directional_reproduction`；
  不是人类金标、盲测或端到端优越性。

## 继续原则

- WS2 已 finalize 并通过独立 verifier；不得重跑、改写或增设 Round 2。
- WS3 仍只能运行已冻结的公开 dev boundary 协议，不得触碰 held-out/test；这次修复只允许处理
  “首个 prediction 前发现的公开 corpus entity lexicon 缺失”。
- 不修改 frozen config、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- 任何重新启动前先同步修复提交到 D: 工作树、确认 worktree clean、清理零 prediction 失败目录，
  再 dry-run guarded starter；只有确认训练允许时才加
  `FAR_BOUNDARY_TRAINING_ALLOWED=1` 与 `--execute`。
- 若恢复或停止 WS2 runner，优先使用 guarded scripts；不删除已有 checkpoint，不重跑已完成样本。
- 仍不得访问 held-out/test，仍不得把 LLM jury 称为真人 IAA。
