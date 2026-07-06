# WS3 外部边界基准选型备忘录

日期：2026-07-06。结论：选 2 个，不为凑数量加入许可或划分不合格的数据。

## 入选

### WikiContradict

- 官方数据页：[IBM Research / Wikipedia Contradict Benchmark](https://huggingface.co/datasets/ibm-research/Wikipedia_contradict_benchmark)
- 固定 revision：`c20e361f985ed480a659b35d98b49f2311fcd174`
- 原始 CSV SHA-256：`cef10054f8aad3e36bca95a0873c2cbb0de8ab4d7b716cadacc5da7aa179ff2b`
- 许可：MIT；253 个真人标注问题，每题含两个矛盾 Wikipedia context 与各自答案；官方未划分
  train/dev/test。
- 导入：seed 2718 分层抽 150。Explicit/Different 72、Implicit/Different 41、
  Explicit/Same 24、Implicit/Same 13。其余 103 条不参与本轮，也不追溯性补跑。
- 机制角色：等可信来源冲突；检验 typed control 能否保留并覆盖两个由上下文分别支持的答案。

### Google CONFLICTS

- 官方仓库：[google-research-datasets/rag_conflicts](https://github.com/google-research-datasets/rag_conflicts)
- 固定 commit：`81ba921dd684a93db41a7e9dda6b6a7c67348a88`
- 原始 JSONL SHA-256：`14559d5c08fde057d7b46783e3345ee5852d6cf6a750f370dc072a0b957fac54`
- 许可：Apache-2.0；458 条，带检索结果、上游冲突类型和部分类型的正确答案。
- 导入：只使用存在唯一 `correct_answer` 的 outdated 62、misinformation 5、no-conflict 83，
  共 150；排除没有可判定正确答案的 complementary/opinion rows。
- 机制角色：把正确答案作为初始答案置于混合检索上下文中，测量 typed control 对时效冲突、
  错误信息和无冲突输入的答案保持/过度修订边界。

两个导入器均生成 dev-only task/corpus、固定配额和独立重算 verifier：
`bench/external/wikicontradict_v1` 与 `bench/external/rag_conflicts_v1`。

## 排除

| 候选 | 排除理由 |
|---|---|
| FaithEval inconsistent/counterfactual | 官方 Hugging Face 只有名为 `test` 的 1,500/1,000 条划分；路线红线禁止把官方 test 当开发集。 |
| ClashEval | 官方仓库/Hugging Face 未声明数据许可证，且部分原始上下文来自 UpToDate 和 Associated Press；不在许可边界不清时复制入公开仓库。 |
| ConflictBank | 官方 README 声称 CC BY-SA 4.0，但仓库没有 LICENSE 文件，Hugging Face `CB_qa` 也没有 license metadata；待作者补齐机器可验证许可后再考虑。 |

Google CONFLICTS 替代原候选表中的 ConflictBank：它同样覆盖结构化 RAG 冲突，但有明确
Apache-2.0、规模可控、上游类型与正确答案，能形成更干净的边界诊断。

## G-P 与主张边界

沿用 Qwen dev 19/60 的不一致率和 +0.078 目标效应，150 配对的 exact McNemar 解析功效
为 0.348（20,000 次、seed 2718 的 Monte Carlo 为 0.344）。低于 0.60，因此两个基准都
必须登记为方向性/描述性边界测绘：正方向和区间可支持“适用区域”描述，null 不证明机制
不存在；不得增加第三基准、改指标或补第二轮追求显著性。

本备忘录只核查公开来源、许可、schema 与聚合分层，不调用模型、不读取项目 held-out/test，
也不把上游真人标注等同于 FAR 的真人 IAA 或 publication-grade human gold。
