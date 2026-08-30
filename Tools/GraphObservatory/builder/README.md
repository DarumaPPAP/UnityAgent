# Graph Observatory Builder

Graph Observatoryのbuilderは、current UnityAgent canonical contractsからderived graph artifactsを生成します。

## Flow

```text
Policy / Orchestration / Context / Runtime / Persistence / Eval
                         ↓
                  Graph Builder
                         ↓
              derived JSON artifacts
                         ↓
              Graph Observatory UI
```

Context viewのcurrent inputは `Context/Packs/*.yaml` です。legacy `.ai` sourceをcurrent inputとして使用しません。

## Rules

- Graph outputはderived view。
- canonical contractがsource of truth。
- Node / Edgeにprovenanceを保持する。
- Missing relationを推測で補わない。
- Visualizationからcanonical contractを直接mutationしない。
- Empty graphをcanonical inputが存在しない証拠として扱わず、input path/schema mismatchを疑う。
