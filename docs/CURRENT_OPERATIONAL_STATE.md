# FAR 当前运行状态

状态时间：2026-07-09 09:40 CST
适用范围：WS3 外部 boundary dev 测绘（Windows GPU / D: 盘 / `boundary_v1`）

## 当前结论

- WS2 三个 family 已全部完成并正常退出；本地 release 已 finalize，独立
  verifier 返回 `valid=true`、`errors=[]`、`gate_f_passed=true`、
  `direction_consistent=true`。
- WS3 已做一次受控启动尝试，但在首个 WikiContradict calibration sample 写出任何
  prediction 前 fail-closed；`far-boundary.service` 已停止，`far-ollama-boundary.service`
  也处于 inactive。当前没有有效 boundary checkpoint 或 manifest。
- WS3 失败根因为公开 boundary corpus 的 `entities` 字段为空，而 frozen
  `qwen_boundary.yaml` 启用了正式 typed stack 的 corpus-entity lexicon。修复方向是在
  runner 中从公开 corpus 文档标题/正文派生非金标实体词表；不读取 `reference_answers`、
  不访问 held-out/test、不关闭 frozen typed component。
- WS2 Mistral、Google 与 Meta 三个 family 已完整完成。Google/Gemma 从原有 2 条 checkpoint
  安全恢复后，两组校准均完成 5/5、两组正式臂均完成 60/60，并写出 Google family
  manifest。随后 Meta/Llama 通过 offline 与在线 digest preflight 后按冻结顺序完成。
  没有启动任何 held-out/test 运行。
- 启动与暂停路径：
  1. `scripts/start_windows_family_dev_next.sh google` dry-run 返回 `valid=true`；
  2. 首次授权启动先启动了 `far-ollama-family-dev.service`，但
     `FAR_FAMILY_DEV_REQUIRE_OLLAMA=1` digest preflight 因 Ollama 冷启动 `/api/tags`
     超时而 fail-closed，未启动 family-dev；
  3. Ollama 响应后确认 `gemma2:9b` digest 为
     `ff02c3702f322b9e075e9568332d96c0a7028002f1a5a056e0a6784320a4db0b`；
  4. 重新运行
     `FAR_FAMILY_DEV_TRAINING_ALLOWED=1 scripts/start_windows_family_dev_next.sh google --execute`
     后，offline preflight 与 digest preflight 均为 `valid=true`，随后启动
     `far-family-dev@google.service`；
  5. 收到“今天晚上不能训练了，明天再训练”后，相关服务已安全停止；第二天收到
     “继续”后重新执行只读 preflight 和显式授权启动，从已有 checkpoint 续跑。
- 恢复时发现旧版 preparer 会把远端工作树切到最新 main，但 WS2 的运行身份冻结在
  `bd57585716b4c046db97311209a0d9f7ec340e6d`。family-dev preflight 因此正确地
  fail-closed。未改写任何 checkpoint；在确认工作树干净后，将其安全恢复为该冻结提交的
  detached 状态，复核配置、模型 digest 与运行身份一致后才启动 runner。
- 远端 `windows-gpu` 最新 service 状态：
  - `far-family-dev@google.service`：`inactive`（正常完成，`NRestarts=0`）；
  - `far-family-dev@meta.service`：`inactive/dead`（正常完成，`NRestarts=0`）；
  - `far-ollama-family-dev.service`：`inactive`（WS2 完成后由 guarded stopper 停止）；
  - `far-family-dev-mistral-resume.service`：`inactive`；
  - `far-family-dev.service`：`inactive`；
  - `far-boundary.service`：`inactive`（首样本前失败后已停止）；
  - `far-ollama-boundary.service`：`inactive`。
- 进程复核已无 `experiments.family_dev`、`experiments.boundary`、`ollama serve`、
  `llama-server` 或 `train.py`；GPU 已释放。
- 远端 D: 工作树 `/mnt/d/FAR-workspace/FAR-longterm` 已切到最新 WS3 main
  `864a6024c717f3a97ebceecdbf42f7bf9bf64c53` 且 clean。下一次启动必须先同步新的修复提交，
  删除仅含旧 `run_identity.json` 的零 prediction 失败目录，再跑 guarded preflight。
- `scripts/prepare_windows_longterm_worktree.sh` 已修正为必须显式选择目标：
  `--family-dev` 保持 WS2 冻结提交，`--latest` 仅供 WS3 或维护使用。
- Meta/Llama 两个校准臂与两个正式臂均已完成，family manifest 已核验。
- D: 盘最近复核：`752G` 总量，约 `688G` 已用，`65G` 可用，使用率 `92%`。
- 未访问 held-out/test；输入 view 仍为 dev-only，`contains_train=false`、
  `contains_test=false`、`test_accessed=false`。

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
