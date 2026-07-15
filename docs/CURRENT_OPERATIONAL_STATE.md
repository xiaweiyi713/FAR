# FAR 当前运行状态

状态时间：2026-07-15 CST
适用范围：长期路线 WS1--WS6、重定位 P0--P14、P6-M 与 standalone paper release；
P14 v2 已完成并释放远端 GPU；当前仅在本机整合代码和文档，不运行或下载模型。

## 当前结论

- 当前接受的无真人重定位 profile 已完成：P6-M 阴性结果是终止证据；人工 P6 已从活动队列移出，
  不再等待复核者或仲裁者。只有未来主动恢复严格人工可映射性/IAA/gold 主张时才重新开启。
- P6-M 三家族双视图正式运行已完成：J1/J2/J3 均为 `434/434`，失败尝试 `0`；
  本地确定性 verifier 返回 `valid=true`、`errors=[]`。
- 机器面板稳定性低：J1/J2/J3 分别为 `50/217`、`88/217`、`24/217`；只有
  `15/217`（`0.0691`）形成共识，202 条 contested。该结果不能替代人工 P6，不能报告
  总体可映射率、human IAA/gold 或 H4 confirmation。
- `far-p6m.service` 与 `far-ollama-2plus4.service` 均为 inactive，远端无 P6-M Python、
  Ollama 或 llama-server 进程；本机从未下载或运行模型。
- 原 P6 仍为 217/217 机器预标完成、`ready_to_analyze=false`。这是被保留的非活动严格人工协议；
  没有模型结果写入人工槽位，也不影响当前无真人 profile 的完成状态。
- TMLR 主文和附录已纳入 P5、P6-M 与 P14 结果；paper-readiness v6 会同时校验
  H3 `uncertain`、H5 scoped `equivalent`、P6-M 15/217 共识/202 contested、P14 注册成功及全部
  非真人/非语义/非 test 边界。活动 16 页 PDF 构建无 overfull/未解析引用并已逐页视觉复核；此整合
  没有调用本机模型或 GPU。
- P11 在冻结 prediction 上完成零模型 revision-delta 度量审计。它修复了 whole-answer soft F1
  可给“原错误答案不修改”高分的盲点：FAR raw/typed delta F1 为 `0.145/0.096`，untyped
  conflict arm 为 `0.093/0`，但 CRAG-style 与 Vanilla raw delta F1 更高（`0.307/0.264`），
  且去掉 refutation query 提高到 `0.194`。这只支持“typed control 更可审计”，不支持 FAR
  在词面修订质量上优于广义基线，也不是语义正确率或真人 gold。
- 相同的事后度量在冻结 WS2 predictions 上显示 Mistral/Gemma/Llama raw delta 差均为正，
  合并 `+0.0398`、family-cluster 95% CI `[+0.0133,+0.0536]`；typed delta 合并
  `+0.0816` `[+0.0353,+0.1137]`。该方向性复现不是 WS2 预注册主指标，也不改变以上负面排名。
- P12 进一步对冻结 claim-level revision trace 做零模型审计。Qwen FAR trace delta F1 仅
  `0.0823`；完整覆盖 construction target 的只有 `15/60`，`19/60` 纯 off-target，`12/60`
  无词法目标编辑。typed-minus-untyped trace delta 为 `+0.0481`、95% CI
  `[+0.0084,+0.0998]`，三个 WS2 家族方向也均为正，合并 `+0.0232`
  `[+0.0064,+0.0355]`；但 any-target-hit 差为 `-0.0333` 且区间跨零。这支持更窄的目标对齐
  信号，同时确认绝对修订可靠性和 collateral rewriting 仍是主要风险，不是语义正确率。
- P13 进一步审计冻结输出是否足以支持 selective revision。错误初始答案保留臂的 soft F1
  为 `0.9784`、60/60 越过旧阈值但 delta F1 为 0；reference-dependent 三臂上界只比 always
  typed 高 `+0.0164`。confidence `>=0.90` 的 31 条没有更高 fidelity（delta `0.1386`、
  5/31 target-complete、25/31 collateral）。因此当前瓶颈是 realization quality，不能把
  置信度阈值、reference oracle 或同一 dev replay 写成可部署 selector、校准风险或因果效果。
- P14 v1 在 10/120 时暂停并永久退出分析；它没有 finalized predictions、run manifest 或结果报告，
  checkpoint 保留但不评分，v2 复用行数为 0。v2 在精确 clean commit
  `04b60a75960d24f911bef4889e2639e238457ccd` 上从零完成 120/120。校准选中 15/60；evaluation
  接受 18/60，selected revision-delta F1 `0.4547`，always typed `0.2196`，enrichment `+0.2351`，
  95% CI `[+0.1028,+0.3856]`，注册 outcome 为 `evaluation_success`。推理仅在 `windows-gpu`；
  本机模型、test split、真人复核均未使用。它是生成后 controller，不节省推理，也不是语义安全、
  外部验证或因果 policy effect。
- 当前诊断安装源升级为不可变 `artifacts-v2`：336 文件、44,128,752 bytes、整树 SHA-256
  `362761dc...e92ae`；原 `artifacts-v1` 未覆盖并继续作为 P10-B 历史快照。
- 活动 TMLR 路线现有独立的 `scripts/solo_paper_release_check.sh`：在 clean commit 上用
  `solo-paper` profile 强制绑定 wheel、sdist、SBOM、两个审计报告、两份 readiness 报告、
  P14 JSON/Markdown、TMLR PDF 与 `SOURCE.lock`。它不读取真人/投稿 evidence，也不冒充严格
  AAAI release gate。
- 该门现会把十一项产物打成确定性 `far-solo-paper-release.tar.gz`，二次打包必须 byte-identical；
  配对的 `verify_solo_paper_release.py` 也必须 byte-identical，并以 `python3 -I` 隔离模式只读
  自身与归档，独立拒绝内容/验证器篡改、额外/危险成员、source-lock 漂移以及任何真人或严格
  投稿主张升级；接收者不需要 checkout、安装 FAR、联网或模型运行时。
- 当前不可变公开版本 [`paper-v2`](https://github.com/xiaweiyi713/FAR/releases/tag/paper-v2) 已绑定
  clean commit `30dc37f62deeaec79d44e23876e1787bd9876174`。归档为 2,363,474 bytes，SHA-256
  `000499205716a93306080ac2bd7a181b5c45df454eb72b65faf70e36e5398217`；从 GitHub 下载到空临时目录
  后，以系统 `python3 -I` 独立验证通过，`valid=true`、`errors=[]`。`paper-v1` 继续保留为 P12
  历史快照，没有被覆盖或改写。

## 既有 WS1--WS6 结论（2026-07-09 冻结）

- WS1--WS6 与 P14 均已有本地可复算证据，长期路线账本返回 `valid=true` 且
  `goal_complete=true`。后续没有已注册的必需 GPU 实验；剩余动作是 commit/push、portable release
  packaging/独立验真与作者自行决定的外部投稿，而不是路线内必需实验或真人复核依赖。
- WS2 三个 family 已全部完成并正常退出；本地 release 已 finalize，独立 verifier 返回
  `valid=true`、`errors=[]`、`gate_f_passed=true`、`direction_consistent=true`。
- WS3 外部 boundary mapping 已完成、同步回本地并 finalize。独立 verifier 返回
  `valid=true`、`errors=[]`、`gate_b_complete=true`、`global_pass_fail=null`、
  `required_claim_level=directional_boundary_mapping`、`publication_gold=false`、
  `human_iaa=false`、`test_accessed=false`。
- WS3 release 覆盖 600 条 formal pipeline predictions 与 20 条 calibration predictions：
  - WikiContradict calibration：`5/5 + 5/5`，formal：`150/150 + 150/150`；
  - Google/RAG conflicts calibration：`5/5 + 5/5`，formal：`150/150 + 150/150`；
  - 8 个 run manifest 均为 `status=complete`、`errors=0`。
- WS3 主结论不是全局胜负：WikiContradict typed-minus-untyped boundary score 为
  `+0.0033`，95% CI `[-0.0067,+0.0167]`；Google/RAG conflicts 为 `-0.0007`，
  95% CI `[-0.0271,+0.0262]`；两个 Holm-adjusted McNemar p 均为 `1.0`。
  预注册假设中 Google outdated-information 子组正向（`+0.0040`）、no-conflict 子组
  保持安全非劣（`-0.0042 >= -0.03`），Wiki explicit/implicit 预测被反驳。论文应写成
  “弱 A-line/窄边界”，不得写成外部全局 transfer 或 end-to-end superiority。
- 远端 `windows-gpu` 上 `far-boundary.service` 与 `far-ollama-boundary.service` 均已停止；
  `far-family-dev@google.service`、`far-family-dev@meta.service`、
  `far-ollama-family-dev.service`、旧 Mistral resume service 也均为 inactive。进程复核无
  `experiments.family_dev`、`experiments.boundary`、`ollama serve`、`llama-server` 或
  `train.py`；GPU compute app 为空，仅剩 `/Xwayland` 桌面基础显存占用约 600MiB。
- 当前没有已注册的必需 GPU 工作；如未来新增实验，仍须等待 `windows-gpu` 严格空闲并通过
  guarded preflight。held-out/test 继续锁定。
- 未访问 held-out/test；仍不得把 LLM jury 或机器标签称为真人 IAA。

## WS2 最终证据

- 输出目录：`/mnt/d/FAR-outputs/family_dev_v1`
- 输入目录：`/mnt/d/FAR-outputs/family_dev_input_v1`
- 当前运行 family：无（WS2 已完成）
- 当前进度：
  - Google `calibration/far`：`5/5`，complete；
  - Google `calibration/minus_typed_conflict`：`5/5`，complete；
  - Google `runs/far`：`60/60`，complete；
  - Google `runs/minus_typed_conflict`：`60/60`，complete；
  - 上述四个 Google checkpoint 均为预期行数、ID 唯一、`errors=0`；Google family
    manifest 的协议、模型、digest、config SHA、冻结 source commit 与安全标志均匹配。
  - Meta/Llama typed 校准：`5/5`、5 个 ID 唯一，complete manifest 已核验为
    `errors=0`、`partial=true`；
  - Meta/Llama untyped 校准：`5/5`、5 个 ID 唯一，complete manifest 已核验为
    `errors=0`、`partial=true`；
  - Meta/Llama 正式 `runs/far`：`60/60`、60 个 ID 唯一、无重复，complete manifest 为
    `errors=0`、`missing_ids=[]`、`partial=false`、`split=dev`，predictions SHA 为
    `9346aaedcfe3463fa0aff9aad78f60b5dd0bb22c2d6a2ce70e4e8ea93fd048bd`；
  - Meta/Llama 正式 `runs/minus_typed_conflict`：`60/60`、60 个 ID 唯一、无重复，
    complete manifest 为 `errors=0`、`missing_ids=[]`、`partial=false`，predictions SHA 为
    `b817be0fce003965c7a68957c752190d3ff1e280d603e5d71d4e50fde8477d9b`；
  - Meta calibration run identity 已复核为冻结提交 `bd575857...`、`git_dirty=false`、
    `llama3.1:8b`、预注册 digest/config SHA、`split=dev`、`limit=5`。
- 当前日志位置：
  - `journalctl --user -u far-family-dev@meta.service -n 120 --no-pager`
  - `journalctl --user -u far-ollama-family-dev.service -n 120 --no-pager`
  - `scripts/watch_windows_family_dev.sh windows-gpu`
- 已完成 family：Mistral
- `mistral / far`
  - checkpoint：`/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/checkpoint.jsonl`
  - 完整性：`60/60` 行、60 个 ID 唯一、无重复组
  - manifest：`status=complete`、`completed=60`、`expected=60`、`partial=false`、`errors=0`
  - predictions SHA：
    `7c72e569a05f131515e85b225c947388ceca87aafef6d00eced580ed683180b5`
- `mistral / minus_typed_conflict`
  - checkpoint：
    `/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/minus_typed_conflict/checkpoint.jsonl`
  - 完整性：`60/60` 行、60 个 ID 唯一、无重复组
  - manifest：`status=complete`、`completed=60`、`expected=60`、`partial=false`、`errors=0`
  - predictions SHA：
    `2643726e3965e86a58cb6afab0223695fc4db7c0df28a3862782c2275d802ae3`
- Mistral family manifest：
  `/mnt/d/FAR-outputs/family_dev_v1/family_manifests/mistral.json`
- 已完成 family：Mistral、Google/Gemma、Meta/Llama。
- 本地最终 release：`diagnostics/family_dev_v1`。G-F 结果为合并连续差
  `+0.0645`、三家族方向 `3/3` 为正、分层 exact McNemar `31 vs 9`、
  `p=0.000680`、家族 cluster bootstrap 95% CI `[+0.0528,+0.0735]`，G-F 通过。
- 由于 G-P 功效仍为 `0.414`，许可结论仍只是 `directional_reproduction`；
  不是人类金标、盲测或端到端优越性。

## 继续原则

- WS2 已 finalize 并通过独立 verifier；不得重跑、改写或增设 Round 2。
- WS3 仍只能运行已冻结的公开 dev boundary 协议，不得触碰 held-out/test；这次修复只允许处理
  “首个 prediction 前发现的公开 corpus entity lexicon 缺失”。
- 不修改 frozen config、模型 digest、样本、指标、G-F/G-P、claim level 或输出目录。
- 任何重新启动前先同步修复提交到 D: 工作树、确认 worktree clean、清理零 prediction 失败目录，
  再 dry-run guarded starter；只有确认训练允许时才加
  `FAR_BOUNDARY_TRAINING_ALLOWED=1` 与 `--execute`。
- 若恢复或停止 WS2 runner，优先使用 guarded scripts；不删除已有 checkpoint，不重跑已完成样本。
- 仍不得访问 held-out/test，仍不得把 LLM jury 称为真人 IAA。
