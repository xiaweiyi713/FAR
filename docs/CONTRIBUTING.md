# 贡献与证据制品约定

FAR 是研究代码与证据仓库。普通代码改动遵循测试、类型检查和 lint；任何可能进入论文、
README 状态表或门禁判定的新制品还必须满足更严格的可重算约定。

## 新实验与预注册

1. 正式比较必须在首个 prediction 行生成前完成预注册，固定数据划分、方法、唯一主指标、
   判定、停止规则、模型/config 身份和偏离流程。
2. 预注册必须绑定 `falsirag-power` 的 G-P 结果；主功效低于 0.60 时，研究级别预先降为
   方向性或描述性，不允许事后以 null 结果证明“没有效应”。
3. 禁止从 `bench/splits/test_inputs.jsonl` 或 RAMDocs test 做开发、调参或错误分析。
4. 机器审计标签、LLM jury 和作者复核不得表述为真人金标、human IAA 或外部盲测。

## 新制品必须有独立 verifier

每个新增的跟踪证据目录都应同时提供：

- 构建器：从已冻结源生成确定性文件集，拒绝非空目录或陈旧残留；
- 独立 verifier：不信任 manifest 自报数字，从源 prediction/score 或输入重新计算关键值，
  核对精确文件集和 SHA-256，并在缺失/多余/不一致时失败关闭；
- 合成单测：至少覆盖成功路径的核心纯函数，以及缺失 release 的 fail-closed 路径；
- provenance：Git commit、配置、模型 digest、数据/协议指纹、划分、样本数、是否访问 test、
  是否为 publication gold/human IAA；
- 复现命令与开发日志：说明 build/verify、偏离、失败和允许的主张边界。

Verifier 不能只重新读取 manifest 后复述其中的布尔值；它必须拥有足以推翻损坏 release 的
独立证据。生成模型输出与确定性重算应分开，后者不得悄悄调用模型。

## 目录约定

- 临时运行、cache、handoff 和本地 PDF 统一放在被忽略的 `outputs/`；旧 `output/` 已停用。
- 可公开、可重算且体积可控的冻结证据放 `diagnostics/`。
- 论文可读的摘要放 `reports/`，并由对应 manifest 绑定 SHA-256。
- `diagnostics/` 超过约 200 MiB 时，优先把大 prediction/checkpoint 迁移到 GitHub Release
  asset 或 Git LFS，仓库内保留 manifest、摘要与校验值；迁移不得破坏已有 verifier。

提交前运行：

```bash
uv run ruff check .
uv run mypy far bench baselines eval experiments tests scripts/package_smoke.py
uv run pytest
uv run python scripts/check_markdown_links.py
```
