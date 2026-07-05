# 2+4 执行手册与当前状态

权威协议为 [`PLAN_2PLUS4.md`](PLAN_2PLUS4.md)。本文件只记录可执行命令和
当前进度，不修改成功判据。活动协议指纹由
`experiments/protocol_2plus4.py` 强制校验。

## 当前状态（2026-07-05）

| 阶段 | 状态 | 权威证据 |
|---|---|---|
| 预注册 | 完成 | 原始提交 `84bbbfd`；所有澄清均为独立 `deviation:` 提交 |
| RAMDocs 导入 | 完成 | 500 题、2766 文档、MIT、HF revision `9c041b…`；350/150 已冻结 |
| RAMDocs dev | 运行中 | Windows GPU 用户服务 `far-ollama-2plus4.service` 与 `far-ramdocs-phase-a.service`；正式替代运行绑定代码提交 `08e04c6`、D: 盘缓存环境和输出目录 `/mnt/d/FAR-outputs/ramdocs_dev_v1`；已启用 `wenyao` systemd linger，并通过完全断开 SSH 的服务 PID、零重启与 checkpoint 增长实测，尚无 `suite_manifest.json` |
| G-A | 待 dev 完成 | 自动选择六基线中 exact match 最高者，执行配对 bootstrap 与 McNemar |
| G-K 陪审团 | 工具完成、执行待 G-A | 六分类主门；失败时按协议降级为二分类 |
| G-S 作者复标 | 工具完成、尚未开始 | round 2 在 round 1 冻结后 14 天前会被代码拒绝 |
| 多模型矩阵 | 工具与配置完成 | Qwen/Mistral/Gemma；只在 jury gold 上生成主张 |
| 一次性 test | 工具完成、禁止提前运行 | intent 必须先提交 Git，再允许 seal 指纹链 |
| 2+4 论文门 | 失败关闭 | `falsirag-jury-paper-readiness` 会列出尚缺制品 |

## RAMDocs

```bash
uv run falsirag-build-ramdocs verify \
  --output-dir bench/external/ramdocs_v1
```

正式 Windows GPU 运行或 checkpoint 恢复使用 D: 盘脚本；它会启动 D: 盘
Ollama、继承 D: 盘 HuggingFace cache，并复用同一个输出目录续跑。长任务由
systemd 用户服务直接持有，不依赖 SSH 创建的 tmux pane scope。启动器会
fail-closed 检查 systemd linger；Windows 登录保活任务应使用
`scripts/keep-wsl-training-online.ps1`：

```bash
mkdir -p ~/.config/systemd/user
cp scripts/systemd/far-ollama-2plus4.service ~/.config/systemd/user/
cp scripts/systemd/far-ramdocs-phase-a.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

随后运行：

```bash
ssh windows-gpu
cd /mnt/d/FAR-workspace/FAR-2plus4
scripts/start_windows_ramdocs_suite.sh
```

查看状态与日志：

```bash
systemctl --user status far-ollama-2plus4.service far-ramdocs-phase-a.service
journalctl --user -fu far-ramdocs-phase-a.service
```

`scripts/systemd/far-tmux-server.service` 只用于其他交互式 tmux 工作；正式
RAMDocs 进程不再依赖 tmux。

启动器会创建 D: 盘授权 marker
`/mnt/d/FAR-runtime/ramdocs_dev_v1.keep-running`。Windows 保活任务只在该
marker 存在且 `suite_manifest.json` 尚未生成时恢复被意外 stop/disable 的
两个正式服务。若 FAR 尚未占用 GPU，watchdog 会先检查显存与利用率；检测到
其他任务时等待，GPU 空闲才启动。suite 完成后自动删除 marker。若需人工
中止，必须先删除 marker，再停止服务：

```bash
rm -f /mnt/d/FAR-runtime/ramdocs_dev_v1.keep-running
systemctl --user disable --now far-ramdocs-phase-a.service far-ollama-2plus4.service
```

运行器只向模型加载当前题目的文档。`test_inputs.jsonl` 只有
`id/question/split`；未给 `--allow-test` 时 test 会被拒绝。

## 陪审团

三个 juror 必须使用同一 packet 和冻结 prompt：

```bash
uv run falsirag-jury-annotate --packet-dir outputs/annotations/falsirag_packet_v1 \
  --config experiments/configs/jury_deepseek.yaml --juror-id J1 \
  --model-family deepseek --output-dir outputs/jury/deepseek

uv run falsirag-jury-annotate --packet-dir outputs/annotations/falsirag_packet_v1 \
  --config experiments/configs/jury_glm.yaml --juror-id J2 \
  --model-family glm --output-dir outputs/jury/glm

uv run falsirag-jury-annotate --packet-dir outputs/annotations/falsirag_packet_v1 \
  --config experiments/configs/jury_llama.yaml --juror-id J3 \
  --model-family meta --output-dir outputs/jury/meta
```

不得使用此前粘贴到聊天中的 DeepSeek key；它应视为已泄露。正式 J1 运行只接受
轮换后通过 `DEEPSEEK_API_KEY` 环境变量注入的密钥，任何 key 都不得写入仓库。

```bash
uv run falsirag-jury-consensus --data-dir bench \
  --juror-dir outputs/jury/deepseek --juror-dir outputs/jury/glm \
  --juror-dir outputs/jury/meta --output-dir outputs/jury/consensus
```

## 作者盲态仲裁

```bash
uv run falsirag-jury-adjudication build-round1 \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --consensus-dir outputs/jury/consensus \
  --output-dir outputs/jury/author_adjudication
```

只编辑 packet 的 `author_annotation`。第一遍冻结后，`build-round2` 会核验时间戳；
不足 14 天直接失败。G-S 通过后使用 `compile` 生成
`bench/labels_jury_v1`，并固定 `jury_gold: true`、`publication_gold: false`。

## 多模型与留出集

Mistral/Gemma 使用 `experiments/configs/mistral_open.yaml` 和
`experiments/configs/gemma_open.yaml`。每个家族只跑 FAR、untyped、CRAG-style、
CounterRefine-style；可用 `scripts/run_2plus4_model_family.sh` 启动固定方法集。
`falsirag-jury-rescore` 用 jury labels 重算，
`falsirag-model-matrix` 汇总三家族方向与回退率。

主模型 Qwen 还必须运行 `falsirag-jury-sensitivity`，对已冻结的 11 种方法同时
报告构造标签、完整 jury gold 和 unanimous-only 三种口径；该报告是最终
readiness 的硬要求。

test 前先用 `falsirag-one-shot prepare` 写 intent，提交该 intent 后才运行预测；
完成后用 `falsirag-one-shot seal` 同时绑定 intent commit、evaluation commit、
suite 指纹和实际评分 manifest。seal 还会核对提交前冻结的样本数与评分数。
该机制是本地防篡改证据，不得称为外部保管盲测。
