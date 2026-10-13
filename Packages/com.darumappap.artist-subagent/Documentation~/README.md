# ArtistSubAgent Backend Unity Package

`Packages/com.darumappap.artist-subagent/`は、ArtistSubAgentのためにUnity Editor内で提供するBackend Packageです。Package IDは`com.darumappap.artist-subagent`、Manifest上の専門Agent IDは`artist_subagent`、Backend IDは`unity_artist_cli`です。Package、Specialist、Backendは別の識別子です。

## Backend command registrations

- `artist.inspect`
- `artist.plan`
- `artist.preview`
- `artist.apply`
- `artist.capture`
- `artist.evaluate`
- `artist.refine`
- `artist.cinematic`
- `artist.history`

このEditor Backendが登録するcommand surfaceは、Hub ManifestがUnityAgent Resolverへ公開するCapability一覧と同義ではありません。現在のManifestが宣言する候補は`artist.camera.inspect`、`artist.camera.refine`、`visual.capture`です。その他のBackend操作は、明示的にManifest化されUnityAgent Runtimeで対応されるまで独立したResolver候補ではありません。

このPackageはGeneric GameObject CRUD、任意C#評価、Automatic Save、Automatic Full Bake、Silent Fallbackを公開しません。`artist.apply`にはUnityAgent Approval TokenとExpected Revisionが必要です。Undoを記録し、Saveは別の承認済み操作に分離します。

## URP LookDev example

Unity 6 URPでは、Intentに`setVolumeLookDev: true`、`volumePostExposure`、`volumeContrast`を指定できます。AdapterはUnity Editor APIでVolume/Profileを解決し、URP `ColorAdjustments`を作成または再利用してUndoとExact Diffを返します。URP以外ではfail-closedです。

```json
{"workflow":"lookdev","targetName":"ArtistCourtyardVolume","setVolumeLookDev":true,"volumePostExposure":-0.6,"volumeContrast":15}
```

このbounded operationは汎用Component / Property Editorではありません。Built-in / HDRPはそれぞれの対応Adapterを使い、URP専用IntentをMutation前に拒否します。Saveは暗黙に行わず、Evidenceを確認してから別の承認済み`save_all`操作を使います。

## Host CLI

Repository RootからHost CLIを利用できます。UnityAgent連携の導入はUnityAgent Control Planeの`doctor → setup plan → approval → setup apply → doctor`を入口とします。以下はBackend固有のCLIであり、UnityAgentの承認済みSetup Planの代替ではありません。

```text
unity artist doctor --project-path <project> --format json --non-interactive
unity artist install --project-path <project> --format json --non-interactive
```

CLIの`unity-artist`実行ファイルと`unity_artist_cli`Backend IDは別の名称です。Backendを導入する操作はUser Setupとして明示され、Capability Resolution時の自動Installではありません。対応Version / Pipelineは[ArtistSubAgent Manifest](../../../Hub/SubAgents/artist_subagent/manifest.yaml)と[Compatibility Matrix](../../../ci/compatibility/support-matrix.yaml)を参照してください。
