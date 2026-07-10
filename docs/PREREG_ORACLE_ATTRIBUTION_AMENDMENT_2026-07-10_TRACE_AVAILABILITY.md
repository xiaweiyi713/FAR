# Stage trace map amendment：retrieval label availability

**对应协议**：`PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10_TRACE_MAP.md`

**发生时点**：stage trace map 首次正式计算在输入完整性检查处停止；尚未产生任何方法分桶、T1 计数或 T2
bootstrap 结果。

## 触发原因

首次计算发现 RAMDocs dev 有 2/350 条没有任何 upstream `document_type=correct` 文档：

| sample_id | category | 文档类型 |
|---|---|---|
| `RAM0008` | `ambiguity_misinformation` | `noise, misinfo, noise` |
| `RAM0060` | `ambiguity_misinformation` | `noise, misinfo, noise, noise` |

在这两条上，`correct-document recall == 0` 既可能表示检索失败，也可能只是 upstream 没有提供可观测 correct
document；把它们计入 `retrieval_miss` 会错误归因。

## 有限修正

1. 保留全部 350 条，不删除、不重标这两条。
2. 在原四桶中新增 `retrieval_unscorable`：EM 为 0，且样本没有 upstream correct document。
3. 若 EM 为 1，仍优先进入 `correct`；同时记录 `retrieval_scorable=false`。
4. `retrieval_miss` 只允许用于至少有一篇 upstream correct document、但其 recall 为 0 的错误。
5. T1 的两个比较 count 不含 `retrieval_unscorable`；T2 的全体分母保留全部 2800 cells，unscorable cells 对
   changed-wrong minus retrieval-miss 的分子贡献为 0。
6. 报告必须给出 unscorable count/proportion，并声明该缺失来自 upstream document-type availability。
7. 任何其他无法归因的 label availability 问题继续失败关闭。

该修正不改变 T1/T2 方向判据，也不提供关于任一方法优劣的结果信息。
