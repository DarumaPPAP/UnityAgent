# Platform and Environment Fallback Policy

UnityAgentが生成するSpec、Plan、Tasks、Goal、Validation Contractへ適用する共通Policy。

## 1. Runtime architecture default

Runtime実装は、ユーザーがPlatform固有統合を明示しない限りPlatform-independentを既定とする。

次を暗黙の依存として追加しない。

- Platform SDK
- Platform固有API
- Platform専用Package
- Platform専用asmdef
- Platform専用define
- Platform Build Support Module
- 特定実機

特定Platform名が性能目標の例として提示されても、対応Platform、Build Target、SDK依存、Module依存、完了条件へ変換しない。

例:

```text
Nintendo Switchでも動く程度に軽くする
```

これは次の意味として扱う。

```text
Performance Class: Low-spec console class
Runtime Architecture: Platform-independent
Platform Dependency: None
```

## 2. Platform target and performance class separation

Specには必要に応じて次を別項目で記録する。

```text
Runtime Platform Policy
Explicit Platform Integration
Performance Class
Measurement Environment
```

`Target Platform`を常時必須入力にしない。

Platform名が必須になるのは次の場合だけとする。

- Platform SDKまたはPlatform APIを使用する
- Platform固有Buildを現在の成果物として要求する
- Platform固有互換性を保証する
- Platform固有性能を保証する

Performance Classの例としてPlatform名を使う場合は、非拘束の参考値であることを明記する。

## 3. Missing environment fallback

Build Support、IL2CPP Module、Platform Module、実機、License、Profiler、Capture Toolなどが利用できないことだけを理由に、Goal全体をBlockedへ移行しない。

Capability不足を検出したら、同一Goal中は一度だけ記録する。同じ存在確認、Build試行、Tool探索を繰り返さない。

```text
Status: DEFERRED_ENVIRONMENT
Unavailable Capability: <capability>
Affected Evidence: <claim only>
Completed Fallbacks: <completed validation>
Remaining Evidence: <named evidence>
```

その後、現在利用可能な最も強い検証へ進む。

1. Static Review
2. Unity Compile
3. EditMode Test
4. PlayMode Test
5. 利用可能なPlayer Build / Runtime
6. Burst Compatibility Review
7. AOT / IL2CPP / Stripping Static Review
8. 利用可能な固定環境でのProfiler計測
9. 対象Moduleまたは実機が利用可能な場合だけ追加Evidence

上位Gateを実行できなくても、独立して実行可能な実装、修正、検証、文書化を継続する。

## 4. Completion states

環境Evidenceと実装完了を分離する。

```text
IMPLEMENTATION_COMPLETE
    実装と現在環境で可能な検証が完了

VALIDATION_PARTIAL
    特定Module、Build、実機Evidenceだけ未取得

VALIDATION_COMPLETE
    要求されたすべてのEvidenceを取得

BLOCKED
    実装自体が不可欠な外部依存によって進行不能
```

Named Platform Evidenceが未取得でも、Platform-independentな実装完了を未完了へ戻さない。

## 5. Valid block conditions

次のいずれかを満たす場合だけBlockedを許可する。

- 実装自体が利用不能なPlatform固有SDKまたはAPIへ必須依存する
- Platform-independent fallbackが存在しない
- ユーザーがNamed Platform Buildまたは実機結果そのものを現在の必須成果物として明示した
- 継続するとRepository、Asset、Save Data、公開互換性を破壊する危険がある
- 必須の仕様判断が衝突し、Agentによる決定が許可されていない

環境不足だけではBlockedにしない。

## 6. Prohibited loop behavior

次を禁止する。

- 同じModule不足を各Taskまたは各Phaseで再確認する
- 実機がないことを繰り返し報告する
- 未取得Evidence一つのために独立Task全体を停止する
- Performance ReferenceをBuild Targetへ変換する
- Optional EvidenceをDone Criteriaへ昇格する
- Editor検証しかできないことを理由に実装を巻き戻す

Capability MatrixはGoal開始時または最初の不足検出時に一度作成し、そのGoal中は再利用する。

## 7. Specification wording

推奨:

```text
Runtime Architecture: Platform-independent
Performance Class: Low-spec console class
Performance Reference: Nintendo Switch-equivalent constraints (non-binding)
Platform-specific dependencies: None
Named-device validation: Optional additional evidence
```

禁止:

```text
Primary Platform: Nintendo Switch
Switch Module required
Switch Build unavailable, therefore Goal blocked
PC IL2CPP Module unavailable, retry until available
```
