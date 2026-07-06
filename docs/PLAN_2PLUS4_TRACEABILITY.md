# 2+4 协议可追溯性矩阵

> 本表是 [`PLAN_2PLUS4.md`](PLAN_2PLUS4.md) 的实现索引，不修改预注册判据。
> “已实现”只表示工具和失败关闭门禁已存在；必须有正式输出才能改为
> “证据完成”。

| 协议条款 | 实现/证据入口 | 当前状态 |
|---|---|---|
| Phase 0 预注册与偏离记录 | `experiments/protocol_2plus4.py`、`docs/DEVELOPMENT_LOG.md` | 证据完成 |
| Phase 0 Mistral/Gemma/Llama 本地 smoke | `scripts/smoke_2plus4_models.sh`、`falsirag-verify-2plus4-smoke`、`diagnostics/model_smoke_2plus4` | 证据完成：Mistral `mistral:7b-instruct`、Google `gemma2:9b`、Meta `llama3.1:8b` 均返回 `SMOKE_OK`；远端与同步后的本地 verifier 均为 `valid:true`，三记录绑定活动协议、配置 SHA-256 与 Ollama digest，并明确 `benchmark_data_accessed:false`、`human_iaa:false` |
| A1 RAMDocs 钉死版本、许可证、指纹和 70/30 切分 | `bench/build/ramdocs.py`、`bench/external/ramdocs_v1/manifest.json` | 证据完成 |
| A2 closed-corpus 映射和初始答案 | `experiments/run_ramdocs.py`、`diagnostics/ramdocs_v1/dev` | 证据完成 |
| A2 strict EM / coverage / wrong exclusion | `eval/ramdocs.py`、`tests/test_ramdocs.py` | 已实现并测试 |
| A2 unsupported sentence proxy | `eval/ramdocs.py` | 已实现并测试 |
| A2 误导文档冲突检出率 | `eval/ramdocs.py` | 已实现并测试 |
| A3 六基线 + typed/untyped | `experiments/ramdocs_suite.py`、`diagnostics/ramdocs_v1/dev` | 8×350 证据完成 |
| A4 G-A、最强基线、bootstrap、McNemar 与停止规则 | `diagnostics/ramdocs_v1/dev/suite_manifest.json`、`diagnostics/ramdocs_v1/error_analysis` | 证据完成；G-A 失败，停止规则触发 |
| A4 Round 2 dev-only 方法迭代 | `experiments/ramdocs_round2.py`、`experiments/ramdocs_round2_error_analysis.py`、`falsirag-round2-failure-readiness`、`diagnostics/ramdocs_v2` | 证据完成且失败关闭：350/350、0 duplicate、verify valid；FAR 0.3086 vs 冻结 Multi-Query 0.3114，配对差 -0.0029、95% CI [-0.0314, 0.0286]、McNemar p=1.0，G-A 第二次失败；release 携带可重算错误分析、`paper_downgrade_required:true`、`test_accessed:false`、`human_iaa:false` |
| B1 三陪审员独立结构化标注 | `experiments/phase_b_gate.py`、`bench/build/jury_annotate.py` | 已实现；annotator 在模型初始化前重算完整 Round 2 verifier，强制 J1/J2/J3 精确模型身份，并以干净 Git/实现/config/G-A/packet/prompt/本地 Ollama digest 绑定可续跑 run identity；当前 G-A 失败，无法执行 |
| B1/B2 Cohen/Fleiss κ、联合多数、二分降级、G-K | `bench/build/jury_consensus.py` | 已实现；consensus 再次重算 G-A 并要求三 juror 绑定一致；二分降级会切换实际投票、联合多数、标签粒度与后续 presence-F1，不把任一陪审员类型冒充类型金标；停止规则阻挡，未执行 |
| B3 作者盲态仲裁、14 天强制间隔、分层 20% 重标、G-S | `bench/build/jury_adjudication.py` | 已实现；停止规则阻挡，未执行 |
| B3 `jury_gold: true` / `publication_gold: false` | `bench/build/jury_adjudication.py` | 已实现；无标签层生成 |
| B4 已冻结 11 方法全量复评 | `experiments/jury_rescore.py` | 已实现；无 jury labels，未执行 |
| B4 构建标签 / jury gold / unanimous-only 敏感性 | `experiments/jury_sensitivity.py` | 已实现；无 jury labels，未执行 |
| B5 Qwen/Mistral/Google 四方法矩阵与 >30% 回退剔除 | `scripts/run_2plus4_model_family.sh`、`experiments/model_matrix.py` | 已实现；停止规则阻挡，未执行 |
| Phase 5 一次性 test intent、commit 绑定、评分数和 seal | `experiments/one_shot.py`、`experiments/runner.py` | 已实现；仅 `--allow-test` 不足以读取 test，必须由已提交且通过 G-A/G-K/G-S/dev 分析校验的 intent 授权；jury labels 的 `phase_b_gate` 必须逐 SHA 对应实际 RAMDocs gate manifest；当前停止规则禁止执行 |
| Phase C 强制披露和禁止声明 | `experiments/jury_paper_readiness.py`、`falsirag-round2-failure-readiness`、`reports/ramdocs_round2_failure_readiness.json` | 成功论文门失败关闭；失败降级门已通过并返回 `ready:true`，重算确认 Round 2 release、错误分析、三模型 smoke、Phase B not run、held-out not run、upstream labels、not human inter-annotator agreement 与 applicability-boundary 披露 |
| RAMDocs / jury 可校验证据包 | `experiments/evidence_2plus4.py` | RAMDocs Round 2 evidence release 已同步到 `diagnostics/ramdocs_v2` 且 verify valid；jury release verifier 已实现从 juror、作者仲裁和三家族源 suite 全链重算，但正式 jury 制品被停止规则阻挡 |

可选 A5 WikiContradict 不是主路径完成门禁，当前未实现。严格 AAAI 人类双标注
档位仍明确为未完成；2+4 只是用外部上游标签和跨家族 LLM 陪审团构成
一个可辩护的单人证据档位，不得宣称为真人 IAA。
