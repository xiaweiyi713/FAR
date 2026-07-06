# FAR 仓库维护基线（2026-07-06）

- `diagnostics/`：约 29 MiB；全仓跟踪文件约 35 MiB，低于路线图约 200 MiB 的迁移阈值。
- 最大单文件约 2.1 MiB，当前无需 Git LFS 或 GitHub Release asset 迁移。
- 历史 `output/` 中两份本地论文 PDF 已移入被忽略的 `outputs/pdf/`；`.gitignore` 明确停用
  `output/`，今后临时生成物统一进入 `outputs/`。
- 新增 `docs/CONTRIBUTING.md`，要求所有新论文证据配独立重算 verifier、合成 fail-closed
  测试、来源指纹和主张边界。
- 新增 Markdown 本地路径检查器并纳入 CI，防止企划、报告和 evidence 交叉引用腐化。

此报告只记录工程状态，不改变 F1–F10、实验判定、标签级别或 held-out 状态。
