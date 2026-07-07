# FAR 当前运行状态

状态时间：2026-07-07 10:13 CST
适用范围：WS2 跨家族 dev 复现（Windows GPU / D: 盘 / `family_dev_v1`）

## 当前结论

- 用户要求的 2026-07-06 夜间暂停窗口已经结束。2026-07-07 10:01 CST，在完成只读
  前置检查后，已从冻结断点恢复 WS2。
- 远端 `windows-gpu` 当前服务：
  - `far-family-dev-mistral-resume.service`：`active`，仅运行 Mistral family；
  - `far-family-dev.service`：`inactive`，不使用其分号串联的三家族命令；
  - `far-ollama-family-dev.service`：`active`。
- 恢复时断点：
  - 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
  - family：`mistral`
  - arm：`far`
  - formal checkpoint：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/checkpoint.jsonl`
  - 已完成行数：`39/60`
  - 尚未生成：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/run_manifest.json`
- 10:13 CST 已完成到 `F0211`，checkpoint 前进到 `44/60` 且 44 个 ID 唯一；runner 随后
  进入 `far: start F0212`。

## 本次恢复前的只读检查

本次恢复已确认：

```bash
scripts/watch_windows_family_dev.sh
```

检查结果满足：

1. 恢复前三个相关服务均为 `inactive`，没有残留 family-dev/Ollama/llama 推理进程；
2. checkpoint 为 Mistral FAR formal `39/60`，39 个 ID 唯一，未生成 manifest；
3. 冻结工作树仍为干净提交 `bd57585716b4c046db97311209a0d9f7ec340e6d`；
4. GPU 无 compute 任务，仅约 552 MiB 桌面占用；
5. D: 盘剩余约 72 GiB；
6. Ollama 的 `mistral:7b-instruct` digest 精确匹配预注册值
   `6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf`；
7. 未访问、未运行任何 held-out/test。

## 恢复原则

- 只能从同一 D: 工作树、同一冻结提交、同一输出目录、同一 checkpoint 恢复。
- 不修改实验代码、配置、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- 若继续使用 transient 恢复，优先只恢复当前未完成的 Mistral family，避免原
  `far-family-dev.service` 的分号串联命令吞掉子命令状态或误串后续 family。
- 恢复后继续把每次停机/恢复写入 `docs/DEVELOPMENT_LOG.md`，并保持 README 状态表准确。

## 最近一次证据

2026-07-07 10:13 CST 只读复核显示：Mistral-only transient service 的 `NRestarts=0`，
runner 与 Ollama 进程均存在；checkpoint 为 44 个唯一 ID，下一条为 `F0212`，最近日志无
traceback、OOM、Xid、磁盘或 schema 错误。这次恢复不修改实验代码、配置、digest、样本、
方法、指标、G-F/G-P、claim level 或输出目录，也不是评分、finalize、Phase B、G-A/G-K/G-S
判定或任何 test 访问。
