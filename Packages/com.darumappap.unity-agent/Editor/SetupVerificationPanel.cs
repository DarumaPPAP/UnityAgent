using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// 既存UnityAgent Setup内の開発用検証入口。HubはRuntimeやInstallerとして扱わない。
    /// 別Editorプロセスで既存P9 fixtureを実行し、測定Evidenceを表示する。
    /// </summary>
    internal static class SetupVerificationPanel
    {
        private static readonly VerificationHubSource s_source = new VerificationHubSource();
        private static bool s_cacheCheckStarted;
        private static bool s_sourceReady;
        private static bool s_preparingSource;
        private static string s_sourceStatus = "検証用Hub環境を確認しています。";
        internal static readonly string[] Fixtures =
        {
            "minimal-6000.6",
            "canonical-full",
            "builtin-smoke",
            "urp-smoke",
            "hdrp-smoke",
            "minimal-6000.3",
        };

        private static bool s_licenseConfirmed;
        private static bool s_graphicsConfirmed;
        private static int s_fixtureIndex;
        private static bool s_running;
        private static string s_status = "NOT_RUN";
        private static string s_message = "未実行。Host CIのGreenは実Unity Editor検証を保証しません。";
        private static string s_outputDirectory = string.Empty;
        private static string s_standardOutput = string.Empty;
        private static string s_standardError = string.Empty;
        private static bool s_showLog;

        [Serializable]
        private sealed class VerificationEvidence
        {
            public string status;
            public string observation;
            public string reason;
        }

        private sealed class Result
        {
            internal string Status;
            internal string Message;
            internal string Output;
            internal string StandardOutput;
            internal string StandardError;
        }

        internal static void Draw()
        {
            using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
            {
                EditorGUILayout.LabelField("5. Unity Verification", EditorStyles.boldLabel);
                EditorGUILayout.LabelField("既存Hub P9 Runnerを使い、別Unity Editorプロセスで検証します。",
                    EditorStyles.wordWrappedMiniLabel);
                EditorGUILayout.Space(4f);
                EditorGUILayout.LabelField("現在のUnity Editor", Application.unityVersion);

                if (!s_cacheCheckStarted)
                {
                    s_cacheCheckStarted = true;
                    Task.Run(() => s_source.TryGetVerifiedCache(out _, out var reason)
                        ? "READY" : reason).ContinueWith(task =>
                    {
                        EditorApplication.delayCall += () =>
                        {
                            s_sourceStatus = task.IsFaulted ? "検証環境の確認に失敗しました。" : task.Result;
                            s_sourceReady = s_sourceStatus == "READY";
                            RepaintSetupWindows();
                        };
                    });
                }
                EditorGUILayout.LabelField("Hub Pin", string.IsNullOrWhiteSpace(s_source.Commit) ?
                    "UNKNOWN" : s_source.Commit.Substring(0, 12));
                EditorGUILayout.LabelField("取得状態", s_preparingSource ? "取得中..." : s_sourceStatus);
                using (new EditorGUI.DisabledScope(s_preparingSource || s_running || s_sourceReady))
                {
                    if (GUILayout.Button("検証環境を取得・更新", GUILayout.Height(26f)))
                    {
                        if (EditorUtility.DisplayDialog("Hub検証環境を準備",
                            "UnityAgent Source Lockで固定したUnitySubAgentHubを取得します。\n\n" +
                            "取得元: DarumaPPAP/UnitySubAgentHub\nCommit: " + s_source.Commit +
                            "\n保存先: UnityAgent管理キャッシュ（Project外）\n\n" +
                            "既存のゲームProject・Source Lock・Providerは変更しません。",
                            "取得", "キャンセル"))
                        {
                            s_preparingSource = true;
                            s_sourceStatus = "取得中...";
                            Task.Run(() => s_source.Prepare()).ContinueWith(task =>
                            {
                                EditorApplication.delayCall += () =>
                                {
                                    s_preparingSource = false;
                                    s_cacheCheckStarted = false;
                                    s_sourceStatus = task.IsFaulted ?
                                        task.Exception.GetBaseException().Message :
                                        string.IsNullOrWhiteSpace(task.Result) ? "取得完了。検証しています。" : task.Result;
                                    RepaintSetupWindows();
                                };
                            });
                        }
                    }
                }

                s_fixtureIndex = EditorGUILayout.Popup("Fixture", s_fixtureIndex, Fixtures);
                s_licenseConfirmed = EditorGUILayout.ToggleLeft(
                    "Unityライセンスが有効で、EditorのCLI実行が可能なことを確認済み", s_licenseConfirmed);
                if (RequiresGraphics(Fixtures[s_fixtureIndex]))
                {
                    s_graphicsConfirmed = EditorGUILayout.ToggleLeft(
                        "GPU / Display / Driverの準備を確認済み", s_graphicsConfirmed);
                }

                EditorGUILayout.HelpBox(
                    "Hub検証環境はSource Lockの固定Commitから取得します。手動Clone不要。" +
                    "Control Plane / SubAgentを自動Installするものではありません。",
                    MessageType.Info);

                using (new EditorGUI.DisabledScope(s_running || s_preparingSource || !s_sourceReady || !s_licenseConfirmed ||
                    (RequiresGraphics(Fixtures[s_fixtureIndex]) && !s_graphicsConfirmed)))
                {
                    if (GUILayout.Button(s_running ? "実行中..." : "選択したUnity検証を実行",
                        GUILayout.Height(28f)))
                    {
                        var fixture = Fixtures[s_fixtureIndex];
                        if (EditorUtility.DisplayDialog("Unity検証を実行",
                            "Pinned Hub: " + s_source.Commit + "\nFixture: " + fixture +
                            "\n\n別Unity Editorプロセスでテストを開始します。" +
                            "\n手元のゲームProjectには変更を加えません。", "実行", "キャンセル"))
                        {
                            Start(fixture);
                        }
                    }
                }

                EditorGUILayout.LabelField("検証状態", s_running ? "RUNNING" : s_status);
                EditorGUILayout.HelpBox(s_message, s_status == "FAIL" ? MessageType.Error :
                    s_status == "BLOCKED_NOT_RUN" ? MessageType.Warning : MessageType.Info);
                using (new EditorGUI.DisabledScope(string.IsNullOrWhiteSpace(s_outputDirectory) ||
                    !Directory.Exists(s_outputDirectory)))
                {
                    if (GUILayout.Button("ログ / Evidenceフォルダを開く"))
                    {
                        EditorUtility.RevealInFinder(s_outputDirectory);
                    }
                }

                s_showLog = EditorGUILayout.Foldout(s_showLog, "検証ログ", true);
                if (s_showLog)
                {
                    var detail = (s_standardOutput + "\n" + s_standardError).Trim();
                    EditorGUILayout.TextArea(string.IsNullOrEmpty(detail) ? "ログはまだありません。" : detail,
                        GUILayout.MinHeight(80f), GUILayout.MaxHeight(180f));
                }

                EditorGUILayout.LabelField(
                    "Full E2E（Control Plane → Editor）、Canary、Player / 実機は別Gateです。",
                    EditorStyles.wordWrappedMiniLabel);
            }
        }

        private static void RepaintSetupWindows()
        {
            foreach (var window in Resources.FindObjectsOfTypeAll<SetupWindow>())
            {
                window.Repaint();
            }
        }

        private static bool RequiresGraphics(string fixture)
        {
            return fixture == "builtin-smoke" || fixture == "urp-smoke" || fixture == "hdrp-smoke";
        }

        private static void Start(string fixture)
        {
            if (s_running)
            {
                return;
            }

            if (Application.platform != RuntimePlatform.WindowsEditor)
            {
                s_status = "BLOCKED_NOT_RUN";
                s_message = "このSetup入口はWindows Editor専用です。Linuxは既存Hubのshell入口を使用してください。";
                return;
            }

            if (!s_source.TryGetVerifiedCache(out var root, out var reason))
            {
                s_status = "BLOCKED_NOT_RUN";
                s_message = "検証用Hubキャッシュを確認できません: " + reason;
                s_sourceReady = false;
                return;
            }

            var output = Path.Combine(Path.GetTempPath(), "UnityAgentVerification",
                Guid.NewGuid().ToString("N"));
            // P9 runnerは独立した一時ProjectとEvidenceを生成する。ゲームProject内へは書き込まない。
            s_outputDirectory = output;
            s_running = true;
            s_status = "RUNNING";
            s_message = "別Editorで実行中です。終了時にP9のevidence.jsonとExitCodeを照合します。";
            s_standardError = string.Empty;
            s_standardOutput = string.Empty;

            var graphicsReady = RequiresGraphics(fixture) && s_graphicsConfirmed;
            var editor = Application.unityVersion == "6000.6.0f1" && fixture != "minimal-6000.3"
                ? EditorApplication.applicationPath : string.Empty;
            Task.Run(() => Execute(root, fixture, output, editor, graphicsReady))
                .ContinueWith(task =>
                {
                    var result = task.IsFaulted
                        ? new Result
                        {
                            Status = "FAIL",
                            Message = task.Exception == null ? "Unknown error" :
                                task.Exception.GetBaseException().Message,
                            Output = output,
                        }
                        : task.Result;
                    EditorApplication.delayCall += () =>
                    {
                        s_running = false;
                        s_status = result.Status;
                        s_message = result.Message;
                        s_outputDirectory = result.Output;
                        s_standardOutput = result.StandardOutput ?? string.Empty;
                        s_standardError = result.StandardError ?? string.Empty;
                        foreach (var window in Resources.FindObjectsOfTypeAll<SetupWindow>())
                        {
                            window.Repaint();
                        }
                    };
                });
        }

        private static Result Execute(string root, string fixture, string output,
            string editor, bool graphicsReady)
        {
            var script = Path.Combine(root, "ci", "scripts", "run-unity-tests.ps1");
            var arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File " +
                Quote(script) + " -Fixture " + Quote(fixture) + " -OutputDirectory " + Quote(output);
            if (!string.IsNullOrWhiteSpace(editor))
            {
                arguments += " -EditorPath " + Quote(editor);
            }

            var start = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = arguments,
                WorkingDirectory = root,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            start.EnvironmentVariables["UNITY_LICENSE_READY"] = "true";
            start.EnvironmentVariables["UNITY_GRAPHICS_READY"] = graphicsReady ? "true" : "false";

            try
            {
                using (var process = new Process { StartInfo = start })
                {
                    var stdout = new StringBuilder();
                    var stderr = new StringBuilder();
                    process.OutputDataReceived += (_, args) =>
                    {
                        if (args.Data != null) stdout.AppendLine(args.Data);
                    };
                    process.ErrorDataReceived += (_, args) =>
                    {
                        if (args.Data != null) stderr.AppendLine(args.Data);
                    };
                    if (!process.Start())
                    {
                        return Failure(output, "PowerShellの起動に失敗しました。");
                    }
                    process.BeginOutputReadLine();
                    process.BeginErrorReadLine();
                    if (!process.WaitForExit(3660000))
                    {
                        try { process.Kill(); } catch (InvalidOperationException) { }
                        return Failure(output,
                            "検証実行の待機時間を超えました。子Editorプロセスが残っていないか確認してください。");
                    }
                    process.WaitForExit();

                    var evidencePath = Path.Combine(output, "evidence.json");
                    if (!File.Exists(evidencePath))
                    {
                        // P9は事前条件不足やPython不在をExitCode=2で返し、Evidenceなしの場合がある。
                        // いずれも観測PASSではない。ExitCodeだけからPASSには昇格させない。
                        if (process.ExitCode == 2)
                        {
                            return new Result
                            {
                                Status = "BLOCKED_NOT_RUN",
                                Message = "実行前の条件不足（Evidence未生成）。ログを確認してください。",
                                Output = output,
                                StandardOutput = stdout.ToString(),
                                StandardError = stderr.ToString(),
                            };
                        }
                        return Failure(output, "Evidenceが生成されていません。ExitCode=" + process.ExitCode,
                            stdout.ToString(), stderr.ToString());
                    }
                    var evidence = JsonUtility.FromJson<VerificationEvidence>(File.ReadAllText(evidencePath));
                    var observedPass = process.ExitCode == 0 && evidence != null &&
                        evidence.status == "PASS" && evidence.observation == "observed";
                    var blocked = process.ExitCode == 2 && evidence != null &&
                        evidence.status == "BLOCKED_NOT_RUN" && evidence.observation == "not_observed";
                    return new Result
                    {
                        Status = observedPass ? "PASS" : blocked ? "BLOCKED_NOT_RUN" : "FAIL",
                        Message = evidence == null ? "Evidenceを解析できませんでした。" :
                            evidence.reason ?? "詳細はEvidenceを確認してください。",
                        Output = output,
                        StandardOutput = stdout.ToString(),
                        StandardError = stderr.ToString(),
                    };
                }
            }
            catch (Exception exception)
            {
                return Failure(output, exception.GetType().Name + ": " + exception.Message);
            }
        }

        private static Result Failure(string output, string message, string stdout = "", string stderr = "")
        {
            return new Result
            {
                Status = "FAIL",
                Message = message,
                Output = output,
                StandardOutput = stdout,
                StandardError = stderr,
            };
        }

        private static string Quote(string value)
        {
            return "\"" + (value ?? string.Empty).Replace("\"", "\\\"") + "\"";
        }
    }
}
