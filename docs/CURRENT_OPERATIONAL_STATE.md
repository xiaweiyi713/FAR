# FAR 当前运行状态

状态时间：2026-07-08 16:46 CST
适用范围：WS2 跨家族 dev 复现（Windows GPU / D: 盘 / `family_dev_v1`）

## 当前结论

- 用户已在第二天重新授权继续训练。远端 `windows-gpu` 上 Google/Gemma 已完整完成并
  正常退出；`far-family-dev@meta.service` 与 `far-ollama-family-dev.service` 当前均为
  `active`。WS3 boundary 仍未启动。
- WS2 Mistral 与 Google 两个 family 已完整完成。Google/Gemma 从原有 2 条 checkpoint
  安全恢复后，两组校准均完成 5/5、两组正式臂均完成 60/60，并写出 Google family
  manifest。随后 Meta/Llama 通过 offline 与在线 digest preflight 后按冻结顺序启动。
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
  - `far-family-dev@meta.service`：`active`（`MainPID=994572`，`NRestarts=0`）；
  - `far-ollama-family-dev.service`：`active`；
  - `far-family-dev-mistral-resume.service`：`inactive`；
  - `far-family-dev.service`：`inactive`；
  - `far-boundary.service` / `far-ollama-boundary.service`：未启动。
- 进程复核可见 Meta `experiments.family_dev` 与 `ollama serve`；
  没有第二个 FAR GPU runner。
- 远端 D: 工作树 `/mnt/d/FAR-workspace/FAR-longterm` 当前故意 detached 在冻结提交
  `bd57585716b4c046db97311209a0d9f7ec340e6d`；`origin/main` 为 `70c5400`。
  WS2 完成前不得切换到最新 main。
- `scripts/prepare_windows_longterm_worktree.sh` 已修正为必须显式选择目标：
  `--family-dev` 保持 WS2 冻结提交，`--latest` 仅供 WS3 或维护使用。
- Meta/Llama 两个校准臂已经完成，runner 已进入正式 `far` 臂；GPU 占用会随 Llama
  加载与推理变化。
- D: 盘最近复核：`752G` 总量，约 `688G` 已用，`65G` 可用，使用率 `92%`。
- 未访问 held-out/test；输入 view 仍为 dev-only，`contains_train=false`、
  `contains_test=false`、`test_accessed=false`。

## 当前 WS2 断点

- 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
- 输入目录：`/mnt/d/FAR-outputs/family_dev_input_v1`
- 当前运行 family：Meta/Llama
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
  - Meta/Llama 正式 `runs/far`：`1/60`、ID 唯一、无重复，runner 正在继续；
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
- 已完成 family：Mistral、Google/Gemma。当前 runner 按预注册顺序执行 Meta/Llama。

## 继续原则

- Meta/Llama 当前为 `active`；保持服务、输出目录、冻结 worktree 和运行身份不变，
  通过 `scripts/watch_windows_family_dev.sh windows-gpu` 只读监控。
- WS2 如需重新准备工作树，只能使用 `scripts/prepare_windows_longterm_worktree.sh
  --family-dev windows-gpu`；不得在 WS2 期间使用 `--latest`。
- Meta/Llama 完成并核验 family manifest 后，才可 finalize 和独立 verify WS2。WS2
  全部完成并释放 GPU 后，WS3 才能用 `--latest` 切换到最新 main。
- 不修改实验代码、配置、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- 任何重新启动前先 dry-run guarded starter；只有确认训练允许时才加
  `FAR_FAMILY_DEV_TRAINING_ALLOWED=1` 与 `--execute`。
- 若恢复或停止 WS2 runner，优先使用 guarded scripts；不删除已有 checkpoint，不重跑已完成样本。
- 仍不得访问 held-out/test，仍不得把 LLM jury 称为真人 IAA。
