# FAR 跨家族 typed/untyped dev 复现 (WS2)

> 机器审计 dev、非真人金标、非盲测、非外部验证；G-P 预先限定为方向性复现。

| 家族 | typed-untyped answer | typed conflict F1 | revision accuracy | 方向 |
|---|---:|---:|---:|---|
| mistral | +0.0528 | +0.4000 | +0.0833 | 正 |
| google | +0.0673 | +0.4000 | +0.2667 | 正 |
| meta | +0.0735 | +0.3742 | +0.2500 | 正 |

## 预注册主判定

- 合并连续差: +0.0645。
- 分层 exact McNemar: candidate-only=31, baseline-only=9, p=0.000680。
- 家族 cluster bootstrap 95% CI: [+0.0528, +0.0735]。
- 正方向家族: 3/3；G-F=`true`。

G-F 不显著不能在 0.414 功效下解释为机制不存在；少于 2/3 家族正方向或合并差非正时，主张按预注册收窄为 Qwen-specific。所有次级指标仅作描述性披露。
