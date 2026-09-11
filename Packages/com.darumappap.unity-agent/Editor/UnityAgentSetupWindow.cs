using System;
using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    internal sealed class UnityAgentSetupWindow : EditorWindow
    {
        private const string CODEX_PLUGIN_SOURCE = "DarumaPPAP/UnityAgent@v0.0.4-beta";
        private const string CODEX_PATH_PREF = "DarumaPPAP.UnityAgent.CodexCliPath";
        private static readonly string[] CODEX_CLI_PRODUCTS = { "codex_cli" };
        private static readonly string[] CODEX_INTEGRATION_PRODUCTS = { "codex_cli", "unity_agent_codex_plugin" };
        private static readonly string[] ALL_PRODUCTS =
        {
            "official_unity_cli",
            "unity_artist_cli",
            "codex_cli",
            "unity_agent_codex_plugin",
        };

        private string hostCommand = "unity-agent";
        private string codexCliPath = string.Empty;
        private string output = string.Empty;
        private string error = string.Empty;
        private string statusMessage = "Codex CLIはまだ確認していません。";
        private MessageType statusType = MessageType.Info;
        private bool showAdvanced;
        private bool showRaw;
        private Vector2 rawScroll;

        [MenuItem("UnityAgent/Setup")]
        private static void Open()
        {
            GetWindow<UnityAgentSetupWindow>("UnityAgent Setup");
        }

        private void OnEnable()
        {
            codexCliPath = EditorPrefs.GetString(CODEX_PATH_PREF, string.Empty);
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("UnityAgent Setup", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "推奨: Codex PluginはこのWindowから導入します。Unity UIはUnityAgent Control Planeを経由し、Providerへ直接Mutationしません。",
                MessageType.Info);

            DrawCodexCliSection();
            EditorGUILayout.Space(8);
            DrawCodexIntegrationSection();
            EditorGUILayout.Space(8);
            DrawResultSection();
            EditorGUILayout.Space(8);
            DrawAdvancedSection();
        }

        private void DrawCodexCliSection()
        {
            EditorGUILayout.LabelField("Codex CLI", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "Unity Editorは起動時のPATHを保持するため、後からCodex CLIをインストールすると見つからない場合があります。自動検出はPATHに加えてWindowsの一般的なnpm配置先も確認します。",
                MessageType.None);

            using (new EditorGUILayout.HorizontalScope())
            {
                codexCliPath = EditorGUILayout.TextField("Codex CLI Path", codexCliPath);
                if (GUILayout.Button("自動検出", GUILayout.Width(90)))
                {
                    AutoDetectCodex();
                }
                if (GUILayout.Button("参照...", GUILayout.Width(70)))
                {
                    BrowseCodex();
                }
            }

            if (string.IsNullOrWhiteSpace(codexCliPath))
            {
                EditorGUILayout.HelpBox(
                    "Path未指定。Control PlaneがPATHと一般的なWindows npm配置先から自動検出します。",
                    MessageType.Info);
            }
            else if (File.Exists(codexCliPath))
            {
                EditorGUILayout.HelpBox("使用するCodex CLI: " + codexCliPath, MessageType.Info);
            }
            else
            {
                EditorGUILayout.HelpBox(
                    "指定されたCodex CLIが存在しません。自動検出または参照から選び直してください。\n" + codexCliPath,
                    MessageType.Warning);
            }
        }

        private void DrawCodexIntegrationSection()
        {
            EditorGUILayout.LabelField("Codex Integration", EditorStyles.boldLabel);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("状態を確認"))
                {
                    Run("doctor", CODEX_INTEGRATION_PRODUCTS);
                }
                if (GUILayout.Button("Codex Pluginをインストール / 修復"))
                {
                    InstallCodexPlugin();
                }
            }
        }

        private void DrawResultSection()
        {
            EditorGUILayout.LabelField("Status", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(statusMessage, statusType);

            if (!string.IsNullOrWhiteSpace(error))
            {
                using (new EditorGUILayout.HorizontalScope())
                {
                    GUILayout.FlexibleSpace();
                    if (GUILayout.Button("エラーをコピー", GUILayout.Width(110)))
                    {
                        EditorGUIUtility.systemCopyBuffer = error;
                    }
                }
            }

            showRaw = EditorGUILayout.Foldout(showRaw, "詳細ログ / Raw response", true);
            if (!showRaw)
            {
                return;
            }

            rawScroll = EditorGUILayout.BeginScrollView(rawScroll, GUILayout.MinHeight(180));
            var raw = BuildRawLog();
            EditorGUILayout.TextArea(raw, GUILayout.ExpandHeight(true));
            EditorGUILayout.EndScrollView();
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("詳細ログをコピー"))
                {
                    EditorGUIUtility.systemCopyBuffer = raw;
                }
                if (GUILayout.Button("クリア"))
                {
                    output = string.Empty;
                    error = string.Empty;
                    statusMessage = "ログをクリアしました。";
                    statusType = MessageType.Info;
                }
            }
        }

        private void DrawAdvancedSection()
        {
            showAdvanced = EditorGUILayout.Foldout(showAdvanced, "Advanced", true);
            if (!showAdvanced)
            {
                return;
            }

            hostCommand = EditorGUILayout.TextField("Control Plane command", hostCommand);
            EditorGUILayout.HelpBox(
                "通常は unity-agent のままで使用します。Unity EditorからPATHを解決できない場合だけunity-agent.exeの絶対Pathを指定してください。",
                MessageType.Info);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("全Toolchain Doctor"))
                {
                    Run("doctor", ALL_PRODUCTS);
                }
                if (GUILayout.Button("全Toolchain Plan"))
                {
                    Run("plan", ALL_PRODUCTS);
                }
            }
        }

        private void AutoDetectCodex()
        {
            error = string.Empty;
            var projectPath = Directory.GetParent(Application.dataPath).FullName;
            var success = UnityAgentControlPlaneClient.TryRun(
                "doctor",
                projectPath,
                hostCommand,
                CODEX_CLI_PRODUCTS,
                string.Empty,
                string.Empty,
                string.Empty,
                string.Empty,
                out output,
                out error);

            var detected = ExtractProductLocation(output, "codex_cli");
            if (!string.IsNullOrEmpty(detected))
            {
                codexCliPath = detected;
                EditorPrefs.SetString(CODEX_PATH_PREF, codexCliPath);
                statusMessage = "Codex CLIを検出しました。\n" + codexCliPath;
                statusType = MessageType.Info;
            }
            else
            {
                statusMessage = BuildReadableMessage(success, output, error);
                statusType = MessageType.Warning;
            }
            Repaint();
        }

        private void BrowseCodex()
        {
            var initialDirectory = string.Empty;
            if (!string.IsNullOrWhiteSpace(codexCliPath))
            {
                try
                {
                    initialDirectory = Path.GetDirectoryName(codexCliPath) ?? string.Empty;
                }
                catch (ArgumentException)
                {
                    initialDirectory = string.Empty;
                }
            }

            var selected = EditorUtility.OpenFilePanel("Codex CLIを選択", initialDirectory, string.Empty);
            if (string.IsNullOrWhiteSpace(selected))
            {
                return;
            }

            codexCliPath = selected;
            EditorPrefs.SetString(CODEX_PATH_PREF, codexCliPath);
            statusMessage = "Codex CLI Pathを設定しました。状態を確認してください。\n" + codexCliPath;
            statusType = File.Exists(codexCliPath) ? MessageType.Info : MessageType.Warning;
        }

        private void Run(string operation, string[] products)
        {
            error = string.Empty;
            var projectPath = Directory.GetParent(Application.dataPath).FullName;
            var success = UnityAgentControlPlaneClient.TryRun(
                operation,
                projectPath,
                hostCommand,
                products,
                string.Empty,
                string.Empty,
                string.Empty,
                codexCliPath,
                out output,
                out error);
            SyncDetectedCodexPath(output);
            statusMessage = BuildReadableMessage(success, output, error);
            statusType = ResolveMessageType(success, output, error);
            Repaint();
        }

        private void InstallCodexPlugin()
        {
            error = string.Empty;
            var projectPath = Directory.GetParent(Application.dataPath).FullName;
            EditorUtility.DisplayProgressBar("UnityAgent Setup", "Codex Plugin setup planを確認しています...", 0.25f);
            try
            {
                var planSuccess = UnityAgentControlPlaneClient.TryRun(
                    "plan",
                    projectPath,
                    hostCommand,
                    CODEX_INTEGRATION_PRODUCTS,
                    string.Empty,
                    string.Empty,
                    string.Empty,
                    codexCliPath,
                    out var planOutput,
                    out var planError);

                output = planOutput;
                error = planError;
                SyncDetectedCodexPath(planOutput);
                if (!planSuccess)
                {
                    statusMessage = BuildReadableMessage(false, planOutput, planError);
                    statusType = MessageType.Error;
                    Repaint();
                    return;
                }

                var planId = ExtractPlanId(planOutput);
                if (string.IsNullOrEmpty(planId))
                {
                    error = "Control Plane responseからplan_idを取得できませんでした。";
                    statusMessage = error;
                    statusType = MessageType.Error;
                    Repaint();
                    return;
                }

                if (!RequiresApproval(planOutput))
                {
                    statusMessage = BuildReadableMessage(true, planOutput, string.Empty);
                    statusType = MessageType.Info;
                    EditorUtility.DisplayDialog(
                        "UnityAgent",
                        "UnityAgent Codex Pluginはすでに利用可能です。新しいCodex Threadで利用してください。",
                        "OK");
                    Repaint();
                    return;
                }

                if (!EditorUtility.DisplayDialog(
                        "UnityAgent Codex Plugin",
                        "Codex CLIのユーザースコープへUnityAgent Pluginをインストールします。\n\n" +
                        "Codex: " + (string.IsNullOrWhiteSpace(codexCliPath) ? "自動検出" : codexCliPath) + "\n" +
                        "Source: " + CODEX_PLUGIN_SOURCE + "\n" +
                        "MutationはUnityAgent Control Plane / Installer Provider経由で実行されます。",
                        "インストール",
                        "キャンセル"))
                {
                    return;
                }

                var planPath = Path.Combine(
                    Path.GetTempPath(),
                    "unityagent-codex-plan-" + Guid.NewGuid().ToString("N") + ".json");
                try
                {
                    File.WriteAllText(planPath, planOutput);
                    var approvalRef = "unity-ui-codex-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss");
                    EditorUtility.DisplayProgressBar("UnityAgent Setup", "Codex Pluginをインストールしています...", 0.7f);
                    var applySuccess = UnityAgentControlPlaneClient.TryRun(
                        "apply",
                        projectPath,
                        hostCommand,
                        CODEX_INTEGRATION_PRODUCTS,
                        planId,
                        approvalRef,
                        planPath,
                        codexCliPath,
                        out output,
                        out error);
                    statusMessage = BuildReadableMessage(applySuccess, output, error);
                    statusType = ResolveMessageType(applySuccess, output, error);
                    if (!applySuccess)
                    {
                        Repaint();
                        return;
                    }
                }
                finally
                {
                    if (File.Exists(planPath))
                    {
                        File.Delete(planPath);
                    }
                }

                EditorUtility.DisplayDialog(
                    "UnityAgent",
                    "UnityAgent Codex Pluginのインストールが完了しました。\n\nCodexで新しいThreadを開始してPluginを読み直してください。",
                    "OK");
                Repaint();
            }
            finally
            {
                EditorUtility.ClearProgressBar();
            }
        }

        private void SyncDetectedCodexPath(string json)
        {
            if (!string.IsNullOrWhiteSpace(codexCliPath))
            {
                return;
            }
            var detected = ExtractProductLocation(json, "codex_cli");
            if (string.IsNullOrWhiteSpace(detected))
            {
                detected = ExtractCodexCliPath(json);
            }
            if (string.IsNullOrWhiteSpace(detected))
            {
                return;
            }
            codexCliPath = detected;
            EditorPrefs.SetString(CODEX_PATH_PREF, codexCliPath);
        }

        private string BuildRawLog()
        {
            var raw = string.Empty;
            if (!string.IsNullOrWhiteSpace(error))
            {
                raw += "[stderr / error]\n" + error.Trim() + "\n\n";
            }
            if (!string.IsNullOrWhiteSpace(output))
            {
                raw += "[stdout / Control Plane response]\n" + output.Trim();
            }
            return string.IsNullOrWhiteSpace(raw) ? "ログはありません。" : raw;
        }

        private static string BuildReadableMessage(bool success, string json, string processError)
        {
            var combined = (json ?? string.Empty) + "\n" + (processError ?? string.Empty);
            if (combined.IndexOf("codex_cli_override_missing", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "指定したCodex CLI Pathが存在しません。『自動検出』または『参照...』から選び直してください。";
            }
            if (combined.IndexOf("codex_cli_unavailable", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "Codex CLIを検出できません。『自動検出』を試すか、『参照...』から codex.exe / codex.cmd を指定してください。";
            }
            if (combined.IndexOf("plugin_not_installed", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "Codex CLIは検出できています。UnityAgent Codex Pluginはまだインストールされていません。『インストール / 修復』を実行してください。";
            }
            if (combined.IndexOf("plugin_not_enabled", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "UnityAgent Codex Pluginは存在しますが無効です。『インストール / 修復』を実行してください。";
            }
            if (combined.IndexOf("plugin_version_mismatch", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "UnityAgent Codex PluginのVersionが現在のUnityAgentと一致しません。『インストール / 修復』を実行してください。";
            }
            if (combined.IndexOf("marketplace name 'unity-agent' is already owned", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "Codex Marketplace名 'unity-agent' が別Sourceに使われています。安全のため自動上書きを停止しました。詳細ログを確認してください。";
            }
            if (Regex.IsMatch(json ?? string.Empty, "\\\"approval_required\\\"\\s*:\\s*true", RegexOptions.IgnoreCase))
            {
                return "Codex CLIを検出しました。UnityAgent Codex Pluginをインストールする準備ができています。";
            }
            if (Regex.IsMatch(json ?? string.Empty, "\\\"status\\\"\\s*:\\s*\\\"passed\\\"", RegexOptions.IgnoreCase))
            {
                return "確認に成功しました。Codex Integrationは利用可能です。";
            }
            if (!success)
            {
                var reason = ExtractJsonString(json, "reason");
                if (!string.IsNullOrWhiteSpace(reason))
                {
                    return "処理に失敗しました。\n" + reason;
                }
                if (!string.IsNullOrWhiteSpace(processError))
                {
                    return processError.Trim();
                }
                return "処理に失敗しました。『詳細ログ / Raw response』を開いて確認してください。";
            }
            return "処理が完了しました。";
        }

        private static MessageType ResolveMessageType(bool success, string json, string processError)
        {
            if (!success || !string.IsNullOrWhiteSpace(processError))
            {
                return MessageType.Error;
            }
            if (Regex.IsMatch(json ?? string.Empty, "\\\"status\\\"\\s*:\\s*\\\"(unavailable|stale)\\\"", RegexOptions.IgnoreCase))
            {
                return MessageType.Warning;
            }
            return MessageType.Info;
        }

        private static string ExtractPlanId(string json)
        {
            return ExtractJsonString(json, "plan_id");
        }

        private static string ExtractProductLocation(string json, string product)
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return string.Empty;
            }
            var pattern =
                "\\\"product\\\"\\s*:\\s*\\\"" + Regex.Escape(product) +
                "\\\"(?s:.*?)\\\"location\\\"\\s*:\\s*\\\"(?<value>(?:\\\\.|[^\\\"])*)\\\"";
            var match = Regex.Match(json, pattern, RegexOptions.IgnoreCase);
            return match.Success ? DecodeJsonString(match.Groups["value"].Value) : string.Empty;
        }

        private static string ExtractCodexCliPath(string json)
        {
            return ExtractJsonString(json, "codex_cli_path");
        }

        private static string ExtractJsonString(string json, string key)
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return string.Empty;
            }
            var pattern =
                "\\\"" + Regex.Escape(key) + "\\\"\\s*:\\s*\\\"(?<value>(?:\\\\.|[^\\\"])*)\\\"";
            var match = Regex.Match(json, pattern, RegexOptions.IgnoreCase);
            return match.Success ? DecodeJsonString(match.Groups["value"].Value) : string.Empty;
        }

        private static string DecodeJsonString(string value)
        {
            return (value ?? string.Empty)
                .Replace("\\\\", "\\")
                .Replace("\\\"", "\"")
                .Replace("\\/", "/")
                .Replace("\\n", "\n")
                .Replace("\\r", "\r")
                .Replace("\\t", "\t");
        }

        private static bool RequiresApproval(string json)
        {
            return Regex.IsMatch(json ?? string.Empty, "\\\"approval_required\\\"\\s*:\\s*true", RegexOptions.IgnoreCase);
        }
    }
}
