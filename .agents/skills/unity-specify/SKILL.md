---
name: unity-specify
description: Unity新機能または仕様変更の要件を整理し、検証可能なspec.mdを作成する。実装コードは書かない。
---

# Unity Specify

1. `Specs/ProjectProfile.md`と`Specs/ProjectConstitution.md`を読む。
2. 目的、背景、対象環境、機能要件、非機能要件、対象外、制約、受け入れ条件、未決定事項を整理する。
3. 要件へ`FR-xxx`、非機能要件へ`NFR-xxx`、受け入れ条件へ`AC-xxx`を付ける。
4. 「高速」「軽量」「安全」を検証方法へ変換する。
5. 判断できない内容は未決定事項へ残す。
6. 仕様策定中は実装コードを書かない。
7. 成果物を`Specs/<FeatureName>/spec.md`へ保存し、`Specs/INDEX.md`へ追加する。
