# FAR 当前运行状态

状态时间：2026-07-07 12:10 CST
适用范围：WS2 跨家族 dev 复现（Windows GPU / D: 盘 / `family_dev_v1`）

## 当前结论

- 2026-07-07 中午停训窗口结束后，已按恢复规则从同一 D: 工作树、同一冻结提交、同一输出目录、
  同一 checkpoint 恢复 WS2 Mistral family。
- 远端 `windows-gpu` 当前服务：
  - `far-family-dev-mistral-resume.service`：`active`，`MainPID=11393`，`NRestarts=0`；
  - `far-ollama-family-dev.service`：`active`，`MainPID=11146`，`NRestarts=0`；
  - `far-family-dev.service`：`inactive`，不使用三家族串联 unit。
- 恢复前确认 Mistral `mistral:7b-instruct` digest 精确匹配冻结值
  `6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf`。
- 恢复后日志显示 runner 已跳过 Mistral FAR formal 的 60 条已完成样本，并在
  `minus_typed_conflict` arm 跳过既有 7 条 checkpoint 后继续运行。最新复核显示
  `F0047` 已完成，checkpoint 为 `8/60`，当前正在 `F0053`。
- GPU 复核显示 Mistral/Ollama 推理占用中；未启动 WS3 boundary、
  Google/Gemma、Meta/Llama 或任何 held-out/test 运行。
- 本地仓库在恢复时位于 `main` 提交 `6eb97b7007198beea19a23fb68c2a3fb7404c1c9`，最近一次
  GitHub Actions 成功。远端正式工作树仍是冻结提交
  `bd57585716b4c046db97311209a0d9f7ec340e6d`。

## 当前 WS2 断点

- 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
- family：`mistral`
- 已完成 arm：`far`
  - checkpoint：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/checkpoint.jsonl`
  - 完整性：`60/60` 行、60 个 ID 唯一、无重复组
  - manifest：`status=complete`、`completed=60`、`expected=60`、`partial=false`、`errors=0`
  - predictions SHA：
    `7c72e569a05f131515e85b225c947388ceca87aafef6d00eced580ed683180b5`
- 当前运行 arm：`minus_typed_conflict`
  - checkpoint：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/minus_typed_conflict/checkpoint.jsonl`
  - 当前进度：`8/60` 行、8 个 ID 唯一、无重复组
  - 最新完成 ID：`F0047`
  - 当前日志位置：已开始 `F0053`
  - manifest：尚未生成
- family manifest：`/mnt/d/FAR-outputs/family_dev_v1/family_manifests/mistral.json` 尚未生成。

## 继续原则

- 继续只允许从同一 D: 工作树、同一冻结提交、同一输出目录、同一 checkpoint 前进。
- 不修改实验代码、配置、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- Mistral `minus_typed_conflict` 完成并生成 family manifest 之前，不启动 Google/Gemma、
  Meta/Llama 或 WS3 boundary 运行。
- 若进程异常停止，先诊断服务状态、GPU、checkpoint 行数/唯一性、日志错误、daemon-reload
  是否复发；不得直接改方法或重跑已完成样本。
- 仍不得访问 held-out/test，仍不得把 LLM jury 称为真人 IAA。
