# Oracle attribution 预注册 amendment（2026-07-10）

**对应冻结协议**：`prereg-oracle-v1` / `docs/PREREG_ORACLE_ATTRIBUTION.md`

**发生时点**：已运行 P1 baseline/revision ceiling 代码；尚未运行或实现 R/D/A，尚未计算 H1–H5 的任何结果。

## 触发原因

冻结协议要求把全部 `gold_answers` 注入答案，并要求 ceiling 在 350 条上达到 1.0。首次运行按约定 fail-closed，发现 9 条任务的 normalized gold 与 wrong 标签直接重叠：

| sample_id | gold/wrong 重叠 |
|---|---|
| `RAM0131` | `Hindi` |
| `RAM0139` | `Linebacker` |
| `RAM0173` | `Ice hockey` / `Ice Hockey` |
| `RAM0204` | `1860` |
| `RAM0243` | `Railway` |
| `RAM0266` | `Division III` |
| `RAM0336` | `Infantry Regiment` |
| `RAM0364` | `Basketball` |
| `RAM0453` | `Woody Allen` |

冻结 scorer 同时要求“包含全部 gold phrases”与“不包含任一 wrong phrase”。上述样本不存在满足两项要求的文本答案；因此全体样本的理论最高 EM 不是 1.0，而是 `341 / 350 = 0.9742857142857143`。

## 有限修正

只修正 P1 ceiling 的验收与输出，不改变样本、baseline、scorer、H1–H5 或 R/D/A 定义：

1. 不删除、不重标这 9 条；baseline 与所有后续全样本指标继续包含它们。
2. 实现必须检测“任一 normalized wrong phrase 被任一 mandatory gold phrase 包含”的不可满足碰撞，并公开 sample ID、gold/wrong pair 与数量。
3. 全样本 revision label-injection ceiling 的预期值改为：
   - EM：`341/350`；
   - coverage：`1.0`；
   - wrong-answer exclusion：`341/350`。
4. 在 341 条 label-feasible 样本上，三个指标仍必须全部为 `1.0`。
5. 任何不能由上述不可满足碰撞解释的 ceiling 失败仍然 fail closed。
6. 报告中使用“label-constrained attainable ceiling”，不得把 0.9743 描述为模型或修订能力损失。

## 影响声明

该修正避免把 upstream 标签自相矛盾错误归因给系统阶段。它降低 ceiling 的数值但不提供 H1–H5 的方向性证据，也不允许排除碰撞样本来提高任一方法的 baseline。
