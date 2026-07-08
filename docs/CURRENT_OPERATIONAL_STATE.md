# FAR 当前运行状态

状态时间：2026-07-08 09:45 CST
适用范围：WS2 跨家族 dev 复现（Windows GPU / D: 盘 / `family_dev_v1`）

## 当前结论

- 按用户最新指令，今晚暂停训练，明天再恢复；远端 `windows-gpu` 上本轮
  Google/Gemma family-dev 和配套 Ollama 已安全停止。
- WS2 Mistral family 已完整完成。Google/Gemma 已按 guarded starter 启动后暂停；
  当前只留下 2 条 `calibration/google/far` checkpoint，没有启动 Meta/Llama、
  WS3 boundary 或任何 held-out/test 运行。
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
  5. 收到“今天晚上不能训练了，明天再训练”后，停止
     `far-family-dev@google.service`、`far-family-dev@meta.service` 和
     `far-ollama-family-dev.service`。
- 远端 `windows-gpu` 最新 service 状态：
  - `far-family-dev@google.service`：`inactive`；
  - `far-family-dev@meta.service`：`inactive`；
  - `far-ollama-family-dev.service`：`inactive`；
  - `far-family-dev-mistral-resume.service`：`inactive`；
  - `far-family-dev.service`：`inactive`；
  - `far-boundary.service` / `far-ollama-boundary.service`：未启动。
- 二次复核没有残留 `experiments.family_dev`、`ollama serve` 或 `llama-server` 进程。
- 远端 D: 工作树 `/mnt/d/FAR-workspace/FAR-longterm` 最近复核仍在旧提交 `bd57585`，
  `origin/main` 也仍为 `bd57585`；本地 `main` 已继续前进。因此明天恢复任何 WS2/WS3
  运行前必须先通过 preparer 同步到届时本地最新提交；具体目标 SHA 由脚本运行时读取，
  不在本状态页硬编码。
- 新增的 `scripts/prepare_windows_longterm_worktree.sh windows-gpu` dry-run 已验证：
  服务全 inactive、远端工作树干净，并只打印 fast-forward 计划；未修改远端文件。
- GPU 停止后最近复核：RTX 4060 Laptop GPU，约 `536 MiB / 8188 MiB` 显存占用。
- D: 盘最近复核：`752G` 总量，`681G` 已用，`71G` 可用，使用率 `91%`。
- 未访问 held-out/test；输入 view 仍为 dev-only，`contains_train=false`、
  `contains_test=false`、`test_accessed=false`。

## 当前 WS2 断点

- 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
- 输入目录：`/mnt/d/FAR-outputs/family_dev_input_v1`
- 当前暂停 family：Google/Gemma
- 当前进度：
  - `calibration/google/far/checkpoint.jsonl`：`2` 行；
  - `calibration/google/minus_typed_conflict/checkpoint.jsonl`：尚未写出；
  - `runs/google/far/checkpoint.jsonl`：尚未写出；
  - `runs/google/minus_typed_conflict/checkpoint.jsonl`：尚未写出。
- 当前日志位置：
  - `journalctl --user -u far-family-dev@google.service -n 120 --no-pager`
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
- 待恢复 family：Google/Gemma。Google/Gemma family manifest 完成并核验前，不启动
  Meta/Llama。

## 继续原则

- 今晚不再训练；明天训练允许后，先运行
  `scripts/prepare_windows_longterm_worktree.sh windows-gpu` dry-run。确认无误后才用
  `FAR_WINDOWS_PREP_ALLOWED=1 scripts/prepare_windows_longterm_worktree.sh --execute windows-gpu`
  将 D: 工作树 fast-forward 到最新 main，再从同一输出目录恢复 WS2 Google/Gemma。
- 不修改实验代码、配置、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- 恢复前先 dry-run guarded starter；只有确认训练允许时才加
  `FAR_FAMILY_DEV_TRAINING_ALLOWED=1` 与 `--execute`。
- 若恢复或停止 WS2 runner，优先使用 guarded scripts；不删除已有 checkpoint，不重跑已完成样本。
- 仍不得访问 held-out/test，仍不得把 LLM jury 称为真人 IAA。
