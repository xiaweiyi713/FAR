# FAR 当前运行状态

状态时间：2026-07-07 17:37 CST
适用范围：WS2 跨家族 dev 复现（Windows GPU / D: 盘 / `family_dev_v1`）

## 当前结论

- 按用户“今天晚上不能训练了，明天再训练”的要求，已停止所有 WS2 family-dev 训练相关
  service；今晚不启动 Google/Gemma、Meta/Llama、WS3 boundary 或任何新模型 prediction。
- 远端 `windows-gpu` 当前 service 状态：
  - `far-family-dev-mistral-resume.service`：`inactive`，`Result=success`，`NRestarts=0`；
  - `far-family-dev.service`：`inactive`，`Result=success`，`NRestarts=0`；
  - `far-ollama-family-dev.service`：`inactive`，`Result=success`，`NRestarts=0`；
  - `far-tmux-server.service`：`active`，只维持 tmux server，不运行 FAR prediction。
- GPU 复核进程表只剩 `/Xwayland` 桌面进程；WSL 报告的桌面显存占用会随 Windows 会话波动
  （最近约 0.8–4.1 GiB），但未发现 `experiments.family_dev`、Ollama runner、
  boundary/family-dev runner 或 `train.py` 进程。
- WS2 Mistral family 已完整完成：FAR formal 与 `minus_typed_conflict` formal 均为
  `60/60`、60 个 ID 唯一、无重复组，两个 run manifest 均为 `status=complete`、
  `partial=false`、`errors=0`。
- Mistral family manifest 已生成在
  `/mnt/d/FAR-outputs/family_dev_v1/family_manifests/mistral.json`，`human_iaa=false`，
  `publication_gold=false`，`test_accessed=false`，`source_commit` 仍为冻结提交
  `bd57585716b4c046db97311209a0d9f7ec340e6d`。
- 未启动 WS3 boundary、Google/Gemma、Meta/Llama 或任何 held-out/test 运行。最近一次已推送
  状态提交 `04835ff` 的 GitHub Actions 已成功。
- 已新增并执行零模型预启动核验脚本
  `scripts/preflight_windows_family_dev_next.sh google`。该脚本只读检查远端 service、
  冻结 worktree、dev-only 输入 view、Mistral predecessor manifest、目标 family 顺序与可选
  Ollama digest；不启动/停止 service、不写远端文件、不运行 prediction。
- 已新增并 dry-run 执行 guarded starter：`scripts/start_windows_family_dev_next.sh google`。
  dry-run 只复用上述 preflight 并打印计划动作；复核显示 `far-family-dev@google.service`
  与 `far-ollama-family-dev.service` 仍为 `inactive/dead`，没有训练进程。
- 预启动核验发现远端尚未安装单 family systemd 模板，已仅部署
  `~/.config/systemd/user/far-family-dev@.service` 并执行 `systemctl --user daemon-reload`；
  `far-family-dev@google.service` 与 `far-family-dev@meta.service` 当前均为 `loaded` 且
  `inactive/dead`。部署模板没有启动训练。

## 当前 WS2 断点

- 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
- 已完成 family：`mistral`
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
- 待运行 family：Google/Gemma、Meta/Llama。今晚暂停，明天恢复前需重新确认 GPU 空闲、
  Ollama digest、D: 空间、正式工作树冻结提交与当前输出目录完整性。
- Google/Gemma 离线 preflight 结果：`valid=true`（未要求 Ollama 在线 digest 检查）。
- `scripts/watch_windows_family_dev.sh windows-gpu` 已能在只读输出中直接显示
  `/mnt/d/FAR-outputs/family_dev_v1/family_manifests/mistral.json`，并列出 WS2/WS3 相关
  service 状态；最新巡检均为 inactive，未见训练进程。

## 继续原则

- 继续只允许从同一 D: 工作树、同一冻结提交、同一输出目录前进。
- 不修改实验代码、配置、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- 明天恢复时，先 dry-run `scripts/start_windows_family_dev_next.sh google`；确认输出仍为
  `valid=true` 且用户允许训练后，再运行
  `scripts/start_windows_family_dev_next.sh google --execute`。该执行模式会按顺序启动
  `far-ollama-family-dev.service`、用
  `FAR_FAMILY_DEV_REQUIRE_OLLAMA=1 scripts/preflight_windows_family_dev_next.sh google`
  精确核验 `gemma2:9b` digest，然后才启动 `far-family-dev@google.service`。
  Google/Gemma family manifest 完成并核验前，不启动 Meta/Llama。
- 若进程异常停止，先诊断服务状态、GPU、checkpoint 行数/唯一性、日志错误、daemon-reload
  是否复发；不得直接改方法或重跑已完成样本。
- 仍不得访问 held-out/test，仍不得把 LLM jury 称为真人 IAA。
