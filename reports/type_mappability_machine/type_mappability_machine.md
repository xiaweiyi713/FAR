# P6-M 跨家族机器本体稳定性审计

> 本报告是机器评审下的 retrospective ontology-stability audit；不替代人工 P6，
> 不报告 human IAA/human gold，不确认 H4。

## 覆盖与稳定性

- Machine consensus: `15/217` (`0.0691`)
- Dispositions: `{"contested": 202, "majority": 14, "unanimous": 1}`
- J1 dual-view stability: `50/217` (`0.2304`)
- J2 dual-view stability: `88/217` (`0.4055`)
- J3 dual-view stability: `24/217` (`0.1106`)

## 模型面板一致性

- view_a mappability Fleiss kappa: `0.1666`
- view_a pairwise Cohen kappas: `{"J1__J2": 0.2260879462761316, "J1__J3": 0.14575779550398837, "J2__J3": 0.27841297316995395}`
- view_a mapped-type macro kappas: `{"J1__J2": 0.16017625178553893, "J1__J3": 0.16716110992091127, "J2__J3": 0.34022621200085673}`
- view_a J1__J2 mapped-type one-vs-rest kappas: `{"causal": -0.01244167962674664, "counter_evidence": 0.0, "definition": 0.1811320754716976, "entity": 0.28441216792026386, "numerical": 0.43852419741255366, "source_reliability": 0.0, "temporal": 0.2296070013210041}`
- view_a J1__J3 mapped-type one-vs-rest kappas: `{"causal": 0.0, "counter_evidence": -0.008520526723471724, "definition": 0.026905829596412474, "entity": 0.3524387734101669, "numerical": 0.4997438524590165, "source_reliability": 0.0, "temporal": 0.2995598407042548}`
- view_a J2__J3 mapped-type one-vs-rest kappas: `{"causal": 0.0, "counter_evidence": 0.0, "definition": 0.22823565795577538, "entity": 0.2545112646005859, "numerical": 0.5261068096088941, "source_reliability": 1.0, "temporal": 0.3727297518407416}`
- view_b mappability Fleiss kappa: `-0.0408`
- view_b pairwise Cohen kappas: `{"J1__J2": 0.042914479777708986, "J1__J3": 0.04189760450915952, "J2__J3": 0.002298850574712904}`
- view_b mapped-type macro kappas: `{"J1__J2": 0.27852533752017955, "J1__J3": 0.1896788656441763, "J2__J3": 0.2278479084706694}`
- view_b J1__J2 mapped-type one-vs-rest kappas: `{"causal": 0.2109090909090898, "counter_evidence": 0.0, "definition": 0.38332807072939656, "entity": 0.3834271839644572, "numerical": 0.6655631029168332, "source_reliability": -0.008130081300813378, "temporal": 0.31457999542229353}`
- view_b J1__J3 mapped-type one-vs-rest kappas: `{"causal": 0.0, "counter_evidence": 0.02340234023402298, "definition": 0.11654825576754231, "entity": 0.21201382508640676, "numerical": 0.704692030057393, "source_reliability": -0.024024024024025103, "temporal": 0.2951196323878941}`
- view_b J2__J3 mapped-type one-vs-rest kappas: `{"causal": 0.0, "counter_evidence": 0.0, "definition": 0.11247443762781198, "entity": 0.40075940628236095, "numerical": 0.7287160895111888, "source_reliability": -0.007428040854227817, "temporal": 0.360413466727552}`

## 稳定投票与 pair sensitivity

- Stable-juror count distribution: `{"0": 87, "1": 99, "2": 30, "3": 1}`
- Mean per-sample normalized vote entropy when defined: `0.1231`; exact stable votes and entropy are preserved in `consensus_rows.jsonl`.
- J1__J2: same stable decision `11/19` (`0.5789`)
- J1__J3: same stable decision `2/3` (`0.6667`)
- J2__J3: same stable decision `4/11` (`0.3636`)

## 共识层可映射性

| 数据集 | consensus n | clean | partial | unmappable | weighted |
|---|---:|---:|---:|---:|---:|
| wikicontradict | 12 | 2 | 10 | 0 | 0.5833 |
| rag_conflicts | 3 | 2 | 1 | 0 | 0.8333 |

### 共识层 typed-minus-untyped delta (sample bootstrap)

`2000` resamples, seed `1729`.

| mappability | n | estimate | lower | upper |
|---|---:|---:|---:|---:|
| clean | 4 | -0.2292 | -0.6875 | 0.0000 |
| partial | 11 | 0.0000 | 0.0000 | 0.0000 |
| unmappable | 0 | n/a | n/a | n/a |

## 外部标签分层 (收敛证据，不是金标)

- `rag_conflicts:{"upstream_conflict_type": "Conflict due to misinformation"}`: consensus `1/5`, weighted `1.0000`, mean delta `0.0000`
- `rag_conflicts:{"upstream_conflict_type": "Conflict due to outdated information"}`: consensus `2/62`, weighted `0.7500`, mean delta `-0.4583`
- `wikicontradict:{"reasoning": "Explicit", "source_relation": "Different"}`: consensus `5/72`, weighted `0.5000`, mean delta `0.0000`
- `wikicontradict:{"reasoning": "Explicit", "source_relation": "Same"}`: consensus `0/24`, weighted `n/a`, mean delta `n/a`
- `wikicontradict:{"reasoning": "Implicit (reasoning required)", "source_relation": "Different"}`: consensus `3/41`, weighted `0.5000`, mean delta `0.0000`
- `wikicontradict:{"reasoning": "Implicit (reasoning required)", "source_relation": "Same"}`: consensus `4/13`, weighted `0.7500`, mean delta `0.0000`

## 描述性 association

- Estimable: `false`
- Not-estimable reason: `one_or_more_frozen_strata_have_no_machine_consensus`
- Spearman rho: `n/a`
- OLS slope: `n/a`
- R²: `n/a`

## 解释边界

- 只有 `15/217` 条样本形成机器共识；共识层比例与 delta 只描述这个选择后的子集，不能外推到全部 217 条。
- 双视图不稳定和 contested 都是冻结协议要求保留的结果，不是删样本、追加模型或事后改写 prompt 的理由。
- 该面板没有提供可替代人工 P6 的广覆盖证据，也不能据此报告总体可映射率、human IAA、gold label 或 H4 confirmation。

所有 contested 样本原样保留；没有第四模型仲裁，也没有把机器结果标成人工证据。
