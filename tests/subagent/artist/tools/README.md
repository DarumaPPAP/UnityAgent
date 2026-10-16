# unity-artist Host CLI Contract Tests

このSuiteは、Unity Editor Licenseを必要とせずに`unity-artist` Host ExecutableのContractを検証します。

- JSON Response Envelope
- Exact Release Matrix
- Approvalの前提条件
- Unity 2022.3 Built-inとURPが現行対象外になる事前Compatibility判定

Host Testが成功しても、Connected Editor / Unity Pipelineでの実行成功は意味しません。Direct EditorやE2EのEvidenceは、Licensed Fixtureを使用するEditor Matrix Workflowと`ci/compatibility/`で確認します。
