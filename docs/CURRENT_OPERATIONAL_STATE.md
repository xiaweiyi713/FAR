# FAR 当前运行状态

状态时间：2026-07-07 11:48 CST
适用范围：WS2 跨家族 dev 复现（Windows GPU / D: 盘 / `family_dev_v1`）

## 当前结论

- 按用户要求，2026-07-07 夜间不继续训练；本轮只做巡检、停机与状态记录，不启动新模型、不运行
  test、不访问 held-out/test。
- 远端 `windows-gpu` 当前 FAR family-dev 相关服务均已停止：
  - `far-family-dev-mistral-resume.service`：`inactive`，`Result=success`，`NRestarts=0`；
  - `far-family-dev.service`：`inactive`，`Result=success`，`NRestarts=0`；
  - `far-ollama-family-dev.service`：`inactive`，`Result=success`，`NRestarts=0`。
- GPU 仍显示约 956 MiB 显存占用，但 `nvidia-smi` 进程表只显示 `/Xwayland`，未发现 FAR
  Python runner、Ollama runner、`train.py` 或 boundary/family-dev 训练进程。
- 本地仓库位于 `main`，工作树干净；最新提交为
  `7faff36d631e12cb6468bec43340289744834acd`，对应 GitHub Actions 最近一次运行成功。

## 当前 WS2 断点

- 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
- family：`mistral`
- 已完成 arm：`far`
  - checkpoint：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/checkpoint.jsonl`
  - 完整性：`60/60` 行、60 个 ID 唯一、无重复组
  - manifest：`status=complete`、`completed=60`、`expected=60`、`partial=false`、`errors=0`
  - predictions SHA：
    `7c72e569a05f131515e85b225c947388ceca87aafef6d00eced580ed683180b5`
- 暂停中的 arm：`minus_typed_conflict`
  - checkpoint：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/minus_typed_conflict/checkpoint.jsonl`
  - 当前进度：`7/60` 行、7 个 ID 唯一、无重复组
  - 最后一条已完成 ID：`F0040`
  - manifest：尚未生成
- family manifest：`/mnt/d/FAR-outputs/family_dev_v1/family_manifests/mistral.json` 尚未生成。

## 恢复原则

- 明天恢复时只能从同一 D: 工作树、同一冻结提交、同一输出目录、同一 checkpoint 继续。
- 恢复前必须重新做只读检查：服务状态、GPU 占用、D: 剩余空间、Mistral digest、checkpoint
  行数/唯一性、日志错误、daemon-reload 是否复发。
- 不修改实验代码、配置、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- Mistral `minus_typed_conflict` 完成并生成 family manifest 之前，不启动 Google/Gemma、
  Meta/Llama 或 WS3 boundary 运行。
- 仍不得把 LLM jury 称为真人 IAA。
