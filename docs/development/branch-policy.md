# Branch Policy

UnityAgentのbranch運用は、長期branchを増やさず `main` を唯一の統合正本として維持する。

機械可読な正本は [`.github/branch-policy.json`](../../.github/branch-policy.json) とする。

| Branch | 用途 | 寿命 |
|---|---|---|
| `main` | 常に統合済みの正本 | 永続 |
| `feature/*` | 新機能 | PR Merge後削除 |
| `fix/*` | 不具合修正 | PR Merge後削除 |
| `chore/*` | CI・Docs・Refactor・Repository整理 | PR Merge後削除 |
| `release/*` | Release準備が本当に必要なときだけ | Release後削除 |

## Naming

作業branchは次の形式だけを使用する。

```text
feature/<lowercase-name>
fix/<lowercase-name>
chore/<lowercase-name>
release/<lowercase-name-or-version>
```

Suffixは小文字英数字を基本とし、`.`、`_`、`-` を使用できる。追加の `/` 階層は作らない。

例:

```text
feature/cloud-development
fix/control-plane-bootstrap
chore/branch-policy
release/v0.0.9-beta
```

以下のprefixは新規branchとして使用しない。

```text
develop/*
codex/*
refactor/*
docs/*
ci/*
test/*
build/*
perf/*
cleanup/*
migration/*
```

新機能は `feature/*`、不具合は `fix/*`、それ以外のRepository作業は原則 `chore/*` に分類する。

## Lifecycle

通常の作業は `main` からbranchを作り、PRのbaseも `main` とする。

```text
main
  └─ feature/* | fix/* | chore/*
          ↓
         PR
          ↓
   Canonical Validation
          ↓
      Squash Merge
          ↓
   head branch自動削除
```

`release/*` は常設の `develop` 代替ではない。Release安定化のため一時branchが本当に必要な場合だけ `main` から作り、Release完了後に削除する。

## Enforcement

- Repository設定はSquash Mergeのみを許可する。
- Merge後のhead branchはGitHubが自動削除する。
- `Tools/BranchPolicy/validate_branch_policy.py` がPolicy定義とbranch名を検証する。
- `UnityAgent CI / Canonical Validation` が全PRでbranch名を検証する。
- Agent / Codexはbranch作成前に用途を分類し、このPolicyに従う。

過去のbranch名やGit履歴はこのPolicy導入のために書き換えない。適用対象は導入後の新規作業branchとする。
