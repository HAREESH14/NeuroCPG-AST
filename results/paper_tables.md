## Table 1: Verification Ablation Results

| Configuration      |   Total Files |   Avg Confidence |   Hallucinations Detected |
|:-------------------|--------------:|-----------------:|--------------------------:|
| None               |            16 |             1    |                         0 |
| Structural (Phase) |            16 |             0.86 |                        49 |
| Semantic (Phase)   |            48 |             0.98 |                         9 |
| Progressive        |            48 |             0.86 |                        88 |

## Table 2: Structural & Semantic Hallucination Distribution

| Hallucination Category   |   Count | % of Total   |
|:-------------------------|--------:|:-------------|
| missing                  |      46 | 52.3%        |
| invented                 |      36 | 40.9%        |
| depth_mismatch           |       3 | 3.4%         |
| invalid_type_transform   |       2 | 2.3%         |
| lost_control_dep         |       1 | 1.1%         |

*Total Hallucinations Detected: 88*
