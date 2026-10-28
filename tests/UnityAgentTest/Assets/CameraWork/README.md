# Camera Work Demo（Unity 6.3）

映画撮影の基本12技法と、参考資料にある**196種類／1,166カット**のカメラワーク構成を試すための、`tests/UnityAgentTest`専用デモ。UnityAgent本番UPMには追加しない。

- 参考: https://jamdesign.co.jp/staffblog/202211cameraworks20221104/
- `Resources/CameraWorkCuts.txt` は原資料にある「No / カメラワーク内訳 / カット数」の一覧。
- `CameraWorkCatalog` は`→`を**連続動作**、隣接する動作語を**同時動作**として解析する。未知の語は例外にする。
- `CameraWork` はCamera Transform / Field of Viewを操作し、`Begin` + `Sample`で任意時点の姿勢を再現する。タイミングは各Phase同じ既定長とする。
- `CameraWorkDemo` は基本12技法と196カットの再生、前後移動、カット数に応じた頻度抽選に対応。
- `CameraWorkDemoMenu` はテスト用Sceneを一時生成する。Sceneは自動保存しない。

## 実行手順

1. Unity Hubから`tests/UnityAgentTest`をUnity **6000.3.12f1**で開く。
2. `Tools > MyTools > Camera Works > Create Demo Scene`を選ぶ。未保存Sceneの保存確認が表示される。
3. Game Viewを表示してPlay。左上のUIから基本技法またはカタログカットを再生する。
4. `Window > General > Test Runner`でEditModeの`CameraWorkTests`、PlayModeの`CameraWorkPlayTests`を実行する。
5. Console、Test Runnerの結果、Editor.logと対象Commit SHAを記録する。

## 動作の定義

| 技法 | 実装 |
| --- | --- |
| フィクス | 微細な手持ち揺れ |
| 完全フィクス | 位置・回転・画角を完全固定 |
| ブレフィクス | 強い手持ち揺れ |
| パン / ティルト | カメラ回転（Yaw / Pitch） |
| ズームイン / アウト | 位置を動かさずFOVを減少 / 増加 |
| ドリーイン / アウト | カメラ前後移動、FOVは維持 |
| トラック | CameraのRight / Up方向へ平行移動 |
| サークルショット | 被写体を中心に軌道移動し被写体へ向く |
| ロール | Camera Forwardを軸に回転（既定360度） |

## 再現精度・制約

- 速度、細かな軌跡、各Phaseの長さ、演者の動き、焦点合わせは原資料にないため復元できない。これは**技法を試す再現デモ**であり映画カットそのものの忠実なレプリカではない。
- 同一Phase内の同時動作は加算・合成する。順番は`→`で区切られたPhaseの順序を維持する。
- 原資料No.69の`ドリアーアウト`は`ドリーアウト`として解析する（原文はデータに保持）。`超スピード`、`早`、`CG特殊`は指定条件に従って解析時に除外する。
- 目視の画作り評価、Unity Compile、EditMode/PlayModeの実測はローカルUnity Editorで確認する。GitHub CIだけでUnity実行成功とは扱わない。
