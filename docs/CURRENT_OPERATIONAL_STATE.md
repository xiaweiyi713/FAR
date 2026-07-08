# FAR 当前运行状态

状态时间：2026-07-08 09:14 CST
适用范围：WS2 跨家族 dev 复现（Windows GPU / D: 盘 / `family_dev_v1`）

## 当前结论

- WS2 Google/Gemma family 已按预注册顺序启动；当前仅运行 Google/Gemma，不启动
  Meta/Llama、WS3 boundary 或任何 held-out/test 运行。
- 启动路径符合 guarded starter：
  1. `scripts/start_windows_family_dev_next.sh google` dry-run 返回 `valid=true`；
  2. 首次授权启动先启动了 `far-ollama-family-dev.service`，但
     `FAR_FAMILY_DEV_REQUIRE_OLLAMA=1` digest preflight 因 Ollama 冷启动 `/api/tags`
     超时而 fail-closed，未启动 family-dev；
  3. Ollama 响应后确认 `gemma2:9b` digest 为
     `ff02c3702f322b9e075e9568332d96c0a7028002f1a5a056e0a6784320a4db0b`；
  4. 重新运行
     `FAR_FAMILY_DEV_TRAINING_ALLOWED=1 scripts/start_windows_family_dev_next.sh google --execute`
     后，offline preflight 与 digest preflight 均为 `valid=true`，随后启动
     `far-family-dev@google.service`。
- 远端 `windows-gpu` 当前 service 状态：
  - `far-family-dev@google.service`：`active`，`MainPID=2715`，`NRestarts=0`；
  - `far-ollama-family-dev.service`：`active`，`MainPID=2329`，`NRestarts=0`；
  - `far-family-dev@meta.service`：`inactive`；
  - `far-family-dev-mistral-resume.service`：`inactive`；
  - `far-family-dev.service`：`inactive`；
  - `far-boundary.service` / `far-ollama-boundary.service`：`inactive`。
- 当前进程：`python -m experiments.family_dev run-family --family google --input-dir
  /mnt/d/FAR-outputs/family_dev_input_v1 --output-dir /mnt/d/FAR-outputs/family_dev_v1`
  与 `ollama serve`。
- GPU 最近复核：RTX 4060 Laptop GPU，约 `626 MiB / 8188 MiB` 显存占用；已看到
  `llama-server` runner（PID 2981）由 Ollama 启动，Google/Gemma 已进入模型服务阶段。
- D: 盘最近复核：`752G` 总量，`681G` 已用，`71G` 可用，使用率 `91%`。
- 未访问 held-out/test；输入 view 仍为 dev-only，`contains_train=false`、
  `contains_test=false`、`test_accessed=false`。

## 当前 WS2 断点

- 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
- 输入目录：`/mnt/d/FAR-outputs/family_dev_input_v1`
- 当前运行 family：Google/Gemma
- 当前进度：
  - `calibration/google/far/checkpoint.jsonl`：尚未写出；
  - `calibration/google/minus_typed_conflict/checkpoint.jsonl`：尚未写出；
  - `runs/google/far/checkpoint.jsonl`：尚未写出；
  - `runs/google/minus_typed_conflict/checkpoint.jsonl`：尚未写出。
- 当前日志位置：
  - `journalctl --user -u far-family-dev@google.service -n 120 --no-pager`
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
- 待运行 family：Meta/Llama。Google/Gemma family manifest 完成并核验前，不启动 Meta/Llama。

## 继续原则

- 只允许从同一 D: 工作树、同一冻结提交、同一输出目录前进。
- 不修改实验代码、配置、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- 当前动作是监控 `far-family-dev@google.service` 直到完成或失败；若异常停止，先诊断
  service 状态、GPU、checkpoint 行数/唯一性、日志错误与 daemon-reload 状态，不直接改方法
  或重跑已完成样本。
- 若需要暂停或停止 WS2 runner，先运行 `scripts/stop_windows_family_dev.sh` dry-run；只有
  确认需要真实停止时才加 `--execute`，只有需要同时停止 WS2 Ollama 时才再加
  `--stop-ollama`。该脚本不停止 WS3 boundary units、不删除 checkpoint。
- 仍不得访问 held-out/test，仍不得把 LLM jury 称为真人 IAA。
