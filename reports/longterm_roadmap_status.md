# FAR 长期路线状态账本

本报告由已跟踪的 manifest、报告和协议指纹生成，用于显示
`docs/PLAN_LONGTERM_OPTIMIZATION.md` 的 WS1-WS6 当前状态。它不是投稿豁免、
不是新实验结果，也不改变 F1-F10、任何门禁、标签级别或 held-out/test 政策。

## 路线指纹

- 路线文件: `docs/PLAN_LONGTERM_OPTIMIZATION.md`
- 活动 SHA-256: `91eb3205fe127271bc5f4882025243d9974a711e311ef074fcbde09aa86e7cf7`
- F1-F10 行存在: `true`

## 工作流状态

| 工作流 | 状态 | 门禁/证据 | 摘要 |
|---|---|---|---|
| WS1 | `complete` | G-R1 | 226 shared RAMDocs errors uniquely bucketed; four hypotheses recorded |
| WS2 | `in_progress_paused` | G-F | Mistral family is complete; next registered family waits for the next training window |
| WS3 | `registered_inputs_ready_pending_predictions` | G-B | two public dev imports and protocol are frozen; no model predictions yet |
| WS4 | `in_progress_waiting_for_ws2_ws3` | paper readiness / claim scope | TMLR mechanism-boundary direction is documented; final paper waits for WS2/WS3 |
| WS5 | `complete` | G-P | power gate is institutionalized; WS2 forced to directional reproduction |
| WS6 | `baseline_complete_ongoing_maintenance` | repository-maintenance audit | tracked diagnostics size and output/outputs hygiene are machine-audited |

## 进度解释

- 已闭合或已建立基线: WS1, WS5, WS6
- 仍未完成: WS2, WS3, WS4
- 总目标完成: `false`
- 当前首要动作: when training is allowed, rerun Google/Gemma preflight with Ollama digest verification and start WS2 Google/Gemma

## 安全边界

- 本报告模型调用: `0`
- 本报告访问 held-out/test: `false`
- 可声称 human IAA: `false`
- 可声称 publication gold: `false`

## 错误

- 无
