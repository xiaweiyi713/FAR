# FAR 当前运行状态

状态时间：2026-07-06 22:04 CST  
适用范围：WS2 跨家族 dev 复现（Windows GPU / D: 盘 / `family_dev_v1`）

## 当前结论

- **今晚不要恢复训练或推理。** 用户明确要求 2026-07-06 晚间不再训练，下一次 WS2
  family-dev 恢复不得早于 2026-07-07。
- 远端 `windows-gpu` 上已停止：
  - `far-family-dev-mistral-resume.service`
  - `far-family-dev.service`
  - `far-ollama-family-dev.service`
- 当前断点：
  - 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
  - family：`mistral`
  - arm：`far`
  - formal checkpoint：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/checkpoint.jsonl`
  - 已完成行数：`39/60`
  - 尚未生成：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/run_manifest.json`

## 明天恢复前的只读检查

恢复前必须先确认：

```bash
scripts/watch_windows_family_dev.sh
```

并至少满足：

1. 三个相关服务没有正在运行，或只有预期的 Ollama 服务；
2. 没有 `python -m experiments.family_dev`、`ollama serve`、`llama-server` 等非预期进程；
3. checkpoint 仍为 Mistral FAR formal `39/60`，没有重复样本或已完成 manifest；
4. GPU 没有被用户其他任务占用；
5. D: 盘仍有足够空间；
6. 不访问、不运行任何 held-out/test。

## 恢复原则

- 只能从同一 D: 工作树、同一冻结提交、同一输出目录、同一 checkpoint 恢复。
- 不修改实验代码、配置、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- 若继续使用 transient 恢复，优先只恢复当前未完成的 Mistral family，避免原
  `far-family-dev.service` 的分号串联命令吞掉子命令状态或误串后续 family。
- 恢复后继续把每次停机/恢复写入 `docs/DEVELOPMENT_LOG.md`，并保持 README 状态表准确。

## 最近一次证据

2026-07-06 晚间只读复核显示：

- 三个相关服务均为 `inactive`；
- checkpoint 为 `39/60`；
- 未见 `family_dev`、Ollama 或 llama 推理进程；
- GPU 进程表仅剩桌面/Xwayland 类残留，不是 FAR 训练/推理。

这不是评分、finalize、Phase B、G-A/G-K/G-S 判定或任何 test 访问。
