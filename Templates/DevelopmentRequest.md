# UnityAgent Development Request

このTemplateは、UnityAgentへローカルUnity Projectの設計・調査・実装を依頼するときに使用します。

すべての項目を毎回埋める必要はありません。Projectから検出できる事実は、可能な限りProject Factとして直接取得します。

---

## 1. やりたいこと

作りたいもの、直したいもの、調査したいことを自然言語で記載してください。

```text
例:
大量のStage Meshを対象にGPU Culling Systemを設計・実装したい。
```

---

## 2. 対象Unity Project

Project Root:

```text
D:\Projects\MyGame\Project
```

原則として `Assets/` だけではなく、Unity Project Rootを指定します。

UnityAgentは必要に応じて次をProject Fact確認対象として扱います。

- `Assets/`
- `Packages/`
- `ProjectSettings/`
- asmdef
- Unity Version
- Package Version
- Renderer / Pipeline設定
- 既存Source / Asset構成

---

## 3. 開発モード

該当するものを選択してください。

- [ ] 設計のみ
- [ ] 調査のみ
- [ ] 設計 + 実装
- [ ] バグ修正
- [ ] Rendering修正
- [ ] Performance改善
- [ ] Portable Package / Tool開発
- [ ] 既存Feature拡張
- [ ] その他

---

## 4. Read Scope

基本推奨:

```text
Project Root全体
```

Project全体を読めることと、Project全体を書き換えてよいことは別です。

Read ScopeはProject Fact、依存関係、既存Owner、Package、設定を正確に把握するために使用します。

---

## 5. Mutation Scope

変更を許可する場所を指定してください。

```text
例:
Assets/Rendering/GPUCulling/**
```

必要になるまで変更を許可しない領域:

- [ ] `Packages/`
- [ ] `ProjectSettings/`
- [ ] Scene / Prefab
- [ ] 既存Public API
- [ ] その他:

指定外の場所へ変更が必要になった場合:

```text
変更理由と影響を説明し、必要ならDesign Reviewへ戻してからMutation Scopeを拡張する。
```

---

## 6. 現在分かっているProject条件

分かるものだけ記載してください。

```text
Unity Version:
Render Pipeline:
Rendering Path:
Target Platform:
Performance Target:
Root Namespace:
主要Package:
関係する既存System:
```

未記入項目は、Projectから検出できる場合は検出した事実を優先します。

Fallback Profileや一般論で検出済みProject Factを上書きしません。

---

## 7. ユーザー側で決まっている制約

Projectから自動検出できない意図を記載してください。

```text
最優先事項:
変更してはいけないもの:
維持する既存Architecture:
Performance Budget:
互換性要件:
UI / UX方針:
命名 / Namespace方針:
その他:
```

---

## 8. 要求

### 必須

- 
- 
- 

### できれば欲しい

- 
- 
- 

### 不要 / Non-goal

- 
- 
- 

---

## 9. Design Review

設計変更を伴うTaskでは、実装前にDesign Reviewを行います。

必要なOutput:

- [ ] Mermaid関連図
- [ ] 設計チェック項目
- [ ] 最終イメージ仕様書
- [ ] 想定File構成
- [ ] Data / Control Flow
- [ ] Acceptance Criteria
- [ ] Non-goal
- [ ] 未解決事項

Design Reviewが必須の場合:

```text
承認されるまでImplementation Mutationへ進まない。
```

調査後に前提が崩れた場合:

```text
Design Reviewへ戻り、関連図・チェック項目・最終イメージ仕様書を更新する。
```

---

## 10. 実装方針

原則:

- 既存Project構造を優先する
- 既存namespace / asmdef / ownershipを確認する
- 新しいManager / Controller / Singleton / static / Profile / ScriptableObjectを必要性なしに追加しない
- 既存Ownerへ責務を追加する方が自然なら、新規Typeを増やさない
- Project Factを推測で作らない
- Mutation Scopeを勝手に広げない

追加の方針がある場合:

```text

```

---

## 11. Verification

必要なものを選択してください。

- [ ] Static Review
- [ ] Compile
- [ ] EditMode Test
- [ ] PlayMode Test
- [ ] Editor Runtime確認
- [ ] Scene確認
- [ ] Rendering確認
- [ ] Profiler
- [ ] Player Build
- [ ] Target Platform
- [ ] 実機
- [ ] Visual Evidence
- [ ] その他:

実行できなかったValidationは成功扱いせず、未検証として報告します。

---

## 12. 完了条件

最低限の完了条件:

- [ ] 要求を満たしている
- [ ] 変更Fileを説明できる
- [ ] Mutation Scopeを逸脱していない
- [ ] Design Reviewとの差分を説明できる
- [ ] 必要なValidationを実行した
- [ ] 未検証項目を明示した
- [ ] 不要なArchitectureを追加していない
- [ ] 成果物を正しいOwner Repository / Projectへ置いている

追加のAcceptance Criteria:

- 
- 
- 

---

## 最小版

詳細Templateを使わず、次だけでも開始できます。

```text
UnityAgentで以下を開発してください。

Project Root:
D:\Projects\MyGame\Project

やりたいこと:
<goal>

Read Scope:
Project Root全体

Mutation Scope:
Assets/<対象Directory>/**

Project Factは実Projectから確認してください。
指定外の変更が必要なら、変更前に理由を説明してください。
設計変更を伴う場合は、実装前にMermaid関連図・チェック項目・最終イメージ仕様書を提示してください。
```

詳細な運用方針は `docs/local-project-development.md` を参照してください。
