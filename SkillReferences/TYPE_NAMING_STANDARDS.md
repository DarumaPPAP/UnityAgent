# UnityAgent Type Naming Standards

## 1. Purpose

UnityAgentが新規Type、明示的Rename、Architecture Proposal上のPlanned Typeを命名するときに使用するSemantic Type NamingのCanonical Sourceである。

NamingはArchitectureの入口ではない。`ENGINEERING_DESIGN_PRINCIPLES.md`でTypeの必要性、責務、粒度、File Structureを確定した後に適用する。

```text
Requirement
↓
Existing Owner
↓
KISS / YAGNI
↓
Cohesion / SRP
↓
Proven DRY / Conditional SOLID
↓
Type / File Structure
↓
Type Naming Contract
```

## 2. Scope

対象:

- class / struct / interface / enum
- MonoBehaviour / ScriptableObject / EditorWindow / CustomEditor
- RendererFeature / ECS System / Component等
- 新規生成Type
- 明示的にRename対象になったType
- Architecture Proposal上のPlanned Type

原則対象外:

- 既存Repository全Typeの一括Rename
- Naming改善だけを理由にしたPublic / Serialized Contract migration
- Member Naming全体の完全AST解析
- 文字数だけによるHard Fail

## 3. Naming Priority

```text
1. Readability
2. Semantic Clarity
3. Responsibility Accuracy
4. Contextual Redundancy Removal
5. Conciseness
```

> Readability over brevity.

短くするために意味を壊さない。長さだけを理由に新しい略語を発明しない。

## 4. Type Necessity Before Naming

新しい名前を考える前にType自体が必要か確認する。

1. Existing Ownerへ自然に含められないか。
2. Property単位でTypeを分割していないか。
3. 複数責務を一つの名前へ詰め込んでいないか。
4. Speculative abstractionではないか。
5. 新規Typeに実在するResponsibility / Owner / Lifetime / Boundary / Split Reasonがあるか。

同じCamera runtime state tracking責務なら、次のようなProperty単位Typeを作らない。

```text
CameraFarClipWatcher
CameraNearClipWatcher
CameraFovWatcher
CameraDepthWatcher
```

独立Typeが本当に必要なら`CameraStateTracker`のように凝集した責務を表す。既存`CameraDebugger`へ自然に含まれるなら新規Type自体を作らない。

## 5. Naming Formula

原則:

```text
[Qualifier?] + Subject + Role
```

例:

```text
CameraDebugger
CameraStateTracker
ShaderVariantAnalyzer
MeshCombineWindow
AudioSourcePool
MaterialPropertyBinder
```

Qualifierは識別に必要な場合だけ付ける。

## 6. Readability Over Brevity

避ける:

```text
CamDbg
MatMgr
ObjUtil
FCPWatcher
```

意味を保つ:

```text
CameraDebugger
MaterialRegistry
ObjectValidator
FarClipWatcher
```

ただし`FarClipWatcher`自体の必要性はNamingより先にArchitectureで判断する。

## 7. Contextual Redundancy

Namespaceが既にContextを与える場合、Type名で同じContextを重複させない。

```csharp
namespace CameraDebugging
{
    public class CameraDebuggingCameraStateTracker
    {
    }
}
```

ではなく、責務が明確なら:

```csharp
namespace CameraDebugging
{
    public class CameraStateTracker
    {
    }
}
```

ただし`StateTracker`まで削ってSubjectが不明になる場合は削りすぎである。

Member NamingはP1の主対象ではないが、明白なContext重複は避ける。`Player`内の`_playerScore`は通常`_score`でよい一方、`ScoreBoard`内の`_playerScore` / `_enemyScore`は識別Qualifierとして妥当である。

## 8. Type Semantics

Class / Struct / Interfaceは原則として名詞または名詞句とする。

処理手順を文章としてType名へ埋め込まない。

避ける:

```text
CameraFarClipChangeDetectAndNotify
LoadAndValidateAsset
```

責務を表す:

```text
CameraStateTracker
AssetLoader
AssetValidator
```

## 9. Role Vocabulary

よく使うRole例:

```text
Analyzer Baker Binder Builder Collector Debugger Driver Exporter Factory
Guard History Importer Pool Presenter Registry Renderer Resolver Router
Scheduler Settings Snapshot State Store Tracker Validator Watcher Window
```

Allow Listではない。Domain固有の正確な用語を優先する。

## 10. Role Suffix Stacking

1 Typeにつき主要Roleは原則1つ。

避ける:

```text
CameraDebugManagerController
AudioServiceManager
ShaderAnalyzerControllerService
AssetRegistryManagerController
```

責務に最も近いRoleへ収束させる。

```text
CameraDebugger
AudioController
ShaderAnalyzer
AssetRegistry
```

## 11. Manager / Controller / Service / System

### Manager

次のような実在責務がある場合のみ使用する。

- 複数Instanceの中央管理
- Resource lifetime管理
- 登録 / 解除
- Ownership管理
- 複数Participant調停

`Pool` / `Registry` / `Scheduler` / `Router` / `Store`等でより具体的に表現できるならそちらを優先する。

### Controller

次のようなFlow / Command責務がある場合に使用する。

- Flow control
- Input control
- State transition
- 複数Componentの命令・調整

単なる監視やデータ取得へ使用しない。

### Service

Application / Feature Boundaryを跨ぐ明確なCapabilityに限定する。単純Wrapperへ使用しない。

### System

原則としてUnity ECS `ISystem` / `SystemBase`、または既存Projectで明確に定義済みのSubsystemへ使用する。

## 12. Vague Names

新規Typeでは次をReviewまたはReject候補とする。

```text
Helper
Util
Utility
Common
General
Universal
Advanced
Flexible
BaseManager
```

単独の`Manager` / `Controller` / `Service` / `System`も責務が不明ならReject対象である。

## 13. Abbreviation Rule

既存Project / Domainで定着した略語は維持できる。

```text
UI GPU CPU LOD URP HDRP MCP RT API SDK
```

UnityAgent自身が名前を短くするためだけに新しい略語を発明しない。

避ける:

```text
CamFCPW
MatPropMgr
DbgCtrl
```

## 14. Length Policy

文字数をHard Limitにしない。

```text
<= 32 chars  通常問題なし
33–40 chars  Naming Review Trigger
> 40 chars   Responsibility / Redundancy Review必須
```

長さ単独ではHard Failにしない。40文字超でもDomain上必要で読みやすく、責務が一つでContext重複がなければ許容できる。

Deterministic Naming Graderでは33文字以上をReview findingとして扱い、Role stacking、Vague Name、明示的Forbidden Identifier等のHard findingとは分離する。

## 15. Conjunction Review

次を含むType名はResponsibility Review Triggerとする。

```text
And Or With Without From To
```

`LoadAndValidateAssetController`のような名前は、複数責務を詰め込んでいないか確認する。正式なDomain Termは例外とする。

## 16. Existing API Preservation

Naming Contractは原則として新規Type、新規Member、新規Architecture Proposal、明示的Renameへ適用する。

Naming改善だけを理由に既存Typeを自動Renameしない。次はCompatibility Analysisと明示的な変更根拠なしに変更しない。

- public API
- Serialized field
- Prefab / Scene参照
- Save Data
- Reflection / string binding
- External API contract

## 17. Deterministic Review Findings

Golden Naming Graderでは次のFinding Codeを使用する。

Hard Error:

```text
NAME001_ROLE_SUFFIX_STACKING
NAME002_VAGUE_TYPE_NAME
NAME003_FORBIDDEN_IDENTIFIER
NAME004_REQUIRED_IDENTIFIER_MISSING
NAME005_UNEXPECTED_NEW_TYPE
```

Warning / Review:

```text
NAME101_LENGTH_REVIEW
NAME102_CONJUNCTION_REVIEW
NAME103_NAMESPACE_REDUNDANCY
NAME104_SUSPECT_ABBREVIATION
```

Warning単独ではGoldenをFailさせない。

## 18. Checklist

新規Typeまたは明示Rename時に確認する。

- [ ] Type / Responsibility / File Structureが先に確定している。
- [ ] Existing Ownerで解決できない理由がある。
- [ ] Property-level Type proliferationではない。
- [ ] 名前が責務を説明している。
- [ ] Readabilityを短さより優先している。
- [ ] Context / Namespace重複を除去した。
- [ ] 新しい略語を発明していない。
- [ ] Role suffixを積み重ねていない。
- [ ] Manager / Controller / Service / Systemに実在責務がある。
- [ ] 長さだけを理由に意味を損なう短縮をしていない。
- [ ] Existing Public / Serialized APIをNaming理由だけで変更していない。

## 19. Final Rule

> Architecture determines whether the Type should exist. Naming makes that justified Type readable and precise.
