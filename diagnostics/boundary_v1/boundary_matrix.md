# FAR 外部冲突边界矩阵 (WS3)

> 两个公开 dev 诊断、Qwen 单模型、方向性功效；不是全局胜负、FAR 真人 IAA 或盲测。

| 基准 | typed-untyped 主分数 | 95% CI | McNemar p | Holm p |
|---|---:|---:|---:|---:|
| wikicontradict | +0.0033 | [-0.0067, +0.0167] | 1.000000 | 1.000000 |
| rag_conflicts | -0.0007 | [-0.0271, +0.0262] | 1.000000 | 1.000000 |

## 预注册预测对照

| 假设 | 结果 |
|---|---|
| B-W-explicit | `contradicted` |
| B-W-implicit | `contradicted` |
| B-G-outdated | `matched` |
| B-G-misinfo | `descriptive_only` |
| B-G-safe | `matched` |

G-B 只表示制品完整，不存在全局通过/失败。功效低于 0.60，null 不能证明无效；任何正方向也只描述该基准、该 dev 抽样和 Qwen 的边界。RAMDocs 双失败保持不变。
