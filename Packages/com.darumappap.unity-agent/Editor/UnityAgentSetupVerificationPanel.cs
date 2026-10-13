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
    internal static class UnityAgentSetupVerificationPanel
    {
        internal const string HubRootPreferenceKey = "DarumaPPAP.UnityAgent.VerificationHubRoot";
        internal static readonly string[] Fixtures =
        {
            "minimal-6000.6",
            "canonical-full",
            "builtin-smoke",
            "urp-smoke",
            "hdrp-smoke",
            "minimal-6000.3",
        };

        private static string s_hubRoot = EditorPrefs.GetString(HubRootPreferenceKey, string.Empty);
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

                using (new EditorGUILayout.HorizontalScope())
                {
                    var changed = EditorGUILayout.TextField("Hub checkout", s_hubRoot);
                    if (!string.Equals(changed, s_hubRoot, StringComparison.Ordinal))
                    {
                        SetHubRoot(changed);
                    }

                    using (new EditorGUI.DisabledScope(s_running))
                    {
                        if (GUILayout.Button("参照...", GUILayout.Width(80f)))
                        {
                            var selected = EditorUtility.OpenFolderPanel(
                                "UnitySubAgentHubのcheckoutを選択", s_hubRoot, string.Empty);
                            if (!string.IsNullOrWhiteSpace(selected))
                            {
                                SetHubRoot(selected);
                            }
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
                    "検証専用のHub checkoutを明示指定してください。Control Plane / Provider / SubAgentの" +
                    "セットアップやインストールは実行しません。各FixtureはHubで固定された別Projectです。",
                    MessageType.Info);

                using (new EditorGUI.DisabledScope(s_running || !s_licenseConfirmed ||
                    (RequiresGraphics(Fixtures[s_fixtureIndex]) && !s_graphicsConfirmed)))
                {
                    if (GUILayout.Button(s_running ? "実行中..." : "選択したUnity検証を実行",
                        GUILayout.Height(28f)))
                    {
                        var fixture = Fixtures[s_fixtureIndex];
                        if (EditorUtility.DisplayDialog("Unity検証を実行",
                            "Hub checkout: " + s_hubRoot + "\nFixture: " + fixture +
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

        private static void SetHubRoot(string root)
        {
            s_hubRoot = root ?? string.Empty;
            EditorPrefs.SetString(HubRootPreferenceKey, s_hubRoot);
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

            string root;
            try
            {
                root = Path.GetFullPath(s_hubRoot ?? string.Empty);
                var script = Path.Combine(root, "ci", "scripts", "run-unity-tests.ps1");
                if (!File.Exists(script) ||
                    !File.Exists(Path.Combine(root, "ci", "unity-matrix.yaml")) ||
                    !File.Exists(Path.Combine(root, "Hub", "Registry", "subagents.yaml")) ||
                    !File.Exists(Path.Combine(root, "Packages", "com.darumappap.artist-subagent", "package.json")))
                {
                    s_status = "BLOCKED_NOT_RUN";
                    s_message = "指定先に正しいUnitySubAgentHubのcheckout / P9 Runnerがありません。";
                    return;
                }
                if (root.IndexOf('"') >= 0 || root.IndexOf('\r') >= 0 || root.IndexOf('\n') >= 0)
                {
                    s_status = "BLOCKED_NOT_RUN";
                    s_message = "Hub checkoutのPathに使用できない文字が含まれています。";
                    return;
                }
            }
            catch (Exception exception)
            {
                s_status = "BLOCKED_NOT_RUN";
                s_message = "Hub checkout Pathが不正です: " + exception.Message;
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
                        foreach (var window in Resources.FindObjectsOfTypeAll<UnityAgentSetupWindow>())
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
