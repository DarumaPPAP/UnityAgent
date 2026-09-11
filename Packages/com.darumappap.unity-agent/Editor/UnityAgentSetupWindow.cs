using System;
using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    internal sealed class UnityAgentSetupWindow : EditorWindow
    {
        private const string CODEX_PLUGIN_SOURCE = "DarumaPPAP/UnityAgent@v0.0.5-beta";
        private static readonly string[] CODEX_INTEGRATION_PRODUCTS = { "codex_cli", "unity_agent_codex_plugin" };
        private static readonly string[] ALL_PRODUCTS =
        {
            "official_unity_cli",
            "unity_artist_cli",
            "codex_cli",
            "unity_agent_codex_plugin",
        };

        private string controlPlanePath = string.Empty;
        private string controlPlanePathSource = string.Empty;
        private string controlPlanePathDiagnostic = string.Empty;
        private string codexCliPath = string.Empty;
        private string codexPathSource = string.Empty;
        private string codexPathDiagnostic = string.Empty;
        private string output = string.Empty;
        private string error = string.Empty;
        private string statusMessage = "UnityAgent環境を確認しています。";
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
            RefreshControlPlanePath();
            RefreshCodexPath();
            UpdateIdleStatus();
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("UnityAgent Setup", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "推奨: このWindowからControl PlaneとCodex CLIを確認し、Codex Pluginを導入します。Provider mutationは必ずUnityAgent Control Planeを経由します。",
                MessageType.Info);

            DrawControlPlaneSection();
            EditorGUILayout.Space(8);
            DrawCodexCliSection();
            EditorGUILayout.Space(8);
            DrawCodexIntegrationSection();
            EditorGUILayout.Space(8);
            DrawResultSection();
            EditorGUILayout.Space(8);
            DrawAdvancedSection();
        }

        private void DrawControlPlaneSection()
        {
            EditorGUILayout.LabelField("UnityAgent Control Plane", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "Unity Hubから起動済みのEditorは、install.ps1が更新したUser PATHをすぐには継承しません。UnityAgentはUser環境変数、User PATH、Python User Scripts、現在のPATHからControl Planeを解決します。",
                MessageType.None);

            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUI.DisabledScope(true))
                {
                    EditorGUILayout.TextField("Resolved Path", string.IsNullOrWhiteSpace(controlPlanePath) ? "Not Found" : controlPlanePath);
                }
                if (GUILayout.Button("再検出", GUILayout.Width(70)))
                {
                    if (UnityAgentControlPlanePathResolver.HasOverride)
                    {
                        UnityAgentControlPlanePathResolver.ClearOverride();
                    }
                    RefreshControlPlanePath();
                    UpdateIdleStatus();
                }
                if (GUILayout.Button("参照...", GUILayout.Width(70)))
                {
                    BrowseControlPlane();
                }
            }

            DrawPathSource(
                UnityAgentControlPlanePathResolver.HasOverride,
                controlPlanePathSource,
                () =>
                {
                    UnityAgentControlPlanePathResolver.ClearOverride();
                    RefreshControlPlanePath();
                    UpdateIdleStatus();
                });

            if (!string.IsNullOrWhiteSpace(controlPlanePath))
            {
                EditorGUILayout.HelpBox("Control Plane detected ✓\n" + controlPlanePath, MessageType.Info);
            }
            else
            {
                EditorGUILayout.HelpBox(
                    string.IsNullOrWhiteSpace(controlPlanePathDiagnostic)
                        ? "Control Plane Not Found。install.ps1を実行するか、『再検出』『参照...』を使用してください。"
                        : controlPlanePathDiagnostic,
                    MessageType.Error);
            }
        }

        private void DrawCodexCliSection()
        {
            EditorGUILayout.LabelField("Codex CLI", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "Codex CLIもShell PATHだけに依存せず、手動Override、環境変数、npm/NVM、一般的な配置先、PATHの順で探します。",
                MessageType.None);

            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUI.DisabledScope(true))
                {
                    EditorGUILayout.TextField("Resolved Path", string.IsNullOrWhiteSpace(codexCliPath) ? "Not Found" : codexCliPath);
                }
                if (GUILayout.Button("再検出", GUILayout.Width(70)))
                {
                    if (UnityAgentCodexPathResolver.HasOverride)
                    {
                        UnityAgentCodexPathResolver.ClearOverride();
                    }
                    RefreshCodexPath();
                    UpdateIdleStatus();
                }
                if (GUILayout.Button("参照...", GUILayout.Width(70)))
                {
                    BrowseCodex();
                }
            }

            DrawPathSource(
                UnityAgentCodexPathResolver.HasOverride,
                codexPathSource,
                () =>
                {
                    UnityAgentCodexPathResolver.ClearOverride();
                    RefreshCodexPath();
                    UpdateIdleStatus();
                });

            if (!string.IsNullOrWhiteSpace(codexCliPath))
            {
                EditorGUILayout.HelpBox("Codex CLI detected ✓\n" + codexCliPath, MessageType.Info);
            }
            else
            {
                EditorGUILayout.HelpBox(
                    string.IsNullOrWhiteSpace(codexPathDiagnostic)
                        ? "Codex CLI Not Found。『再検出』または『参照...』を使用してください。"
                        : codexPathDiagnostic,
                    MessageType.Warning);
            }
        }

        private static void DrawPathSource(bool hasOverride, string source, Action clearOverride)
        {
            if (hasOverride)
            {
                using (new EditorGUILayout.HorizontalScope())
                {
                    EditorGUILayout.LabelField("Source: Manual override");
                    if (GUILayout.Button("Override解除", GUILayout.Width(100)))
                    {
                        clearOverride();
                    }
                }
            }
            else if (!string.IsNullOrWhiteSpace(source))
            {
                EditorGUILayout.LabelField("Source: " + source);
            }
        }

        private void DrawCodexIntegrationSection()
        {
            EditorGUILayout.LabelField("Codex Integration", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(string.IsNullOrWhiteSpace(controlPlanePath)))
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("状態を確認"))
                {
                    Run("doctor", CODEX_INTEGRATION_PRODUCTS);
                }
                using (new EditorGUI.DisabledScope(string.IsNullOrWhiteSpace(codexCliPath)))
                {
                    if (GUILayout.Button("Codex Pluginをインストール / 修復"))
                    {
                        InstallCodexPlugin();
                    }
                }
            }

            if (string.IsNullOrWhiteSpace(controlPlanePath))
            {
                EditorGUILayout.HelpBox("Control Planeが見つかるまでSetup操作は実行できません。", MessageType.Warning);
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
                    UpdateIdleStatus();
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

            using (new EditorGUI.DisabledScope(string.IsNullOrWhiteSpace(controlPlanePath)))
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

        private void RefreshControlPlanePath()
        {
            controlPlanePath = UnityAgentControlPlanePathResolver.Resolve(
                out controlPlanePathSource,
                out controlPlanePathDiagnostic) ?? string.Empty;
            Repaint();
        }

        private void RefreshCodexPath()
        {
            codexCliPath = UnityAgentCodexPathResolver.Resolve(out codexPathSource, out codexPathDiagnostic) ?? string.Empty;
            Repaint();
        }

        private void UpdateIdleStatus()
        {
            if (string.IsNullOrWhiteSpace(controlPlanePath))
            {
                statusMessage = "UnityAgent Control Planeを検出できません。上のControl Plane欄から再検出またはPath指定を行ってください。";
                statusType = MessageType.Error;
                return;
            }
            if (string.IsNullOrWhiteSpace(codexCliPath))
            {
                statusMessage = "Control Planeは利用可能です。Codex CLIを検出できていません。Codex欄から再検出またはPath指定を行ってください。";
                statusType = MessageType.Warning;
                return;
            }
            statusMessage = "Control Plane / Codex CLIを検出しました。状態確認またはPlugin Installを実行できます。";
            statusType = MessageType.Info;
        }

        private void BrowseControlPlane()
        {
            var selected = EditorUtility.OpenFilePanel(
                "UnityAgent Control Planeを選択",
                SafeDirectory(controlPlanePath),
                string.Empty);
            if (string.IsNullOrWhiteSpace(selected))
            {
                return;
            }
            if (!UnityAgentControlPlanePathResolver.TrySetOverride(selected, out var overrideError))
            {
                SetError(overrideError);
                return;
            }
            error = string.Empty;
            RefreshControlPlanePath();
            UpdateIdleStatus();
        }

        private void BrowseCodex()
        {
            var selected = EditorUtility.OpenFilePanel("Codex CLIを選択", SafeDirectory(codexCliPath), string.Empty);
            if (string.IsNullOrWhiteSpace(selected))
            {
                return;
            }
            if (!UnityAgentCodexPathResolver.TrySetOverride(selected, out var overrideError))
            {
                SetError(overrideError);
                return;
            }
            error = string.Empty;
            RefreshCodexPath();
            UpdateIdleStatus();
        }

        private static string SafeDirectory(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return string.Empty;
            }
            try
            {
                return Path.GetDirectoryName(path) ?? string.Empty;
            }
            catch
            {
                return string.Empty;
            }
        }

        private void Run(string operation, string[] products)
        {
            error = string.Empty;
            EnsurePathsBeforeRequest();
            if (string.IsNullOrWhiteSpace(controlPlanePath))
            {
                SetError("UnityAgent Control Planeを検出できません。『再検出』または『参照...』を使用してください。");
                return;
            }

            var projectPath = Directory.GetParent(Application.dataPath).FullName;
            var success = UnityAgentControlPlaneClient.TryRun(
                operation,
                projectPath,
                controlPlanePath,
                products,
                string.Empty,
                string.Empty,
                string.Empty,
                codexCliPath,
                out output,
                out error);
            statusMessage = BuildReadableMessage(success, output, error);
            statusType = ResolveMessageType(success, output, error);
            showRaw |= !success;
            Repaint();
        }

        private void InstallCodexPlugin()
        {
            error = string.Empty;
            EnsurePathsBeforeRequest();
            if (string.IsNullOrWhiteSpace(controlPlanePath))
            {
                SetError("UnityAgent Control Planeを検出できません。Control Plane欄からPathを解決してください。");
                return;
            }
            if (string.IsNullOrWhiteSpace(codexCliPath))
            {
                statusMessage = "Codex CLIが必要です。Codex欄の『再検出』または『参照...』を使用してください。";
                statusType = MessageType.Warning;
                return;
            }

            var projectPath = Directory.GetParent(Application.dataPath).FullName;
            EditorUtility.DisplayProgressBar("UnityAgent Setup", "Codex Plugin setup planを確認しています...", 0.25f);
            try
            {
                var planSuccess = UnityAgentControlPlaneClient.TryRun(
                    "plan", projectPath, controlPlanePath, CODEX_INTEGRATION_PRODUCTS,
                    string.Empty, string.Empty, string.Empty, codexCliPath,
                    out var planOutput, out var planError);
                output = planOutput;
                error = planError;
                if (!planSuccess)
                {
                    statusMessage = BuildReadableMessage(false, planOutput, planError);
                    statusType = MessageType.Error;
                    showRaw = true;
                    return;
                }

                var planId = ExtractJsonString(planOutput, "plan_id");
                if (string.IsNullOrEmpty(planId))
                {
                    SetError("Control Plane responseからplan_idを取得できませんでした。");
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
                    return;
                }

                if (!EditorUtility.DisplayDialog(
                        "UnityAgent Codex Plugin",
                        "Codex CLIのユーザースコープへUnityAgent Pluginをインストールします。\n\n" +
                        "Control Plane: " + controlPlanePath + "\n" +
                        "Codex: " + codexCliPath + "\n" +
                        "Source: " + CODEX_PLUGIN_SOURCE,
                        "インストール",
                        "キャンセル"))
                {
                    return;
                }

                var planPath = Path.Combine(Path.GetTempPath(), "unityagent-codex-plan-" + Guid.NewGuid().ToString("N") + ".json");
                try
                {
                    File.WriteAllText(planPath, planOutput);
                    var approvalRef = "unity-ui-codex-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss");
                    EditorUtility.DisplayProgressBar("UnityAgent Setup", "Codex Pluginをインストールしています...", 0.7f);
                    var applySuccess = UnityAgentControlPlaneClient.TryRun(
                        "apply", projectPath, controlPlanePath, CODEX_INTEGRATION_PRODUCTS,
                        planId, approvalRef, planPath, codexCliPath,
                        out output, out error);
                    statusMessage = BuildReadableMessage(applySuccess, output, error);
                    statusType = ResolveMessageType(applySuccess, output, error);
                    showRaw |= !applySuccess;
                    if (!applySuccess)
                    {
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
            }
            finally
            {
                EditorUtility.ClearProgressBar();
                Repaint();
            }
        }

        private void EnsurePathsBeforeRequest()
        {
            if (string.IsNullOrWhiteSpace(controlPlanePath) || !File.Exists(controlPlanePath))
            {
                RefreshControlPlanePath();
            }
            if (string.IsNullOrWhiteSpace(codexCliPath) || !File.Exists(codexCliPath))
            {
                RefreshCodexPath();
            }
        }

        private void SetError(string message)
        {
            error = message;
            statusMessage = message;
            statusType = MessageType.Error;
            showRaw = true;
            Repaint();
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
                return "指定したCodex CLI Pathが存在しません。Codex欄から選び直すかOverrideを解除してください。";
            }
            if (combined.IndexOf("codex_cli_unavailable", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "Codex CLIを検出できません。Codex欄の『再検出』または『参照...』を使用してください。";
            }
            if (combined.IndexOf("plugin_not_installed", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "Codex CLIは利用可能です。UnityAgent Codex Pluginはまだインストールされていません。";
            }
            if (combined.IndexOf("plugin_not_enabled", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "UnityAgent Codex Pluginは存在しますが無効です。『インストール / 修復』を実行してください。";
            }
            if (combined.IndexOf("plugin_version_mismatch", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "UnityAgent Codex PluginのVersionが現在のUnityAgentと一致しません。『インストール / 修復』を実行してください。";
            }
            if (Regex.IsMatch(json ?? string.Empty, "\\\"approval_required\\\"\\s*:\\s*true", RegexOptions.IgnoreCase))
            {
                return "Control Plane / Codex CLIを確認しました。Pluginをインストールする準備ができています。";
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
                    return "Setupに失敗しました: " + reason;
                }
                return string.IsNullOrWhiteSpace(processError)
                    ? "Setupに失敗しました。詳細ログを確認してください。"
                    : FirstLine(processError);
            }
            return "処理が完了しました。";
        }

        private static MessageType ResolveMessageType(bool success, string json, string processError)
        {
            if (!success)
            {
                return MessageType.Error;
            }
            if (Regex.IsMatch(json ?? string.Empty, "\\\"status\\\"\\s*:\\s*\\\"(?:unavailable|stale)\\\"", RegexOptions.IgnoreCase))
            {
                return MessageType.Warning;
            }
            return MessageType.Info;
        }

        private static string ExtractJsonString(string json, string propertyName)
        {
            var pattern = "\\\"" + Regex.Escape(propertyName) + "\\\"\\s*:\\s*\\\"(?<value>(?:\\\\.|[^\\\"])*)\\\"";
            var match = Regex.Match(json ?? string.Empty, pattern, RegexOptions.IgnoreCase);
            if (!match.Success)
            {
                return string.Empty;
            }
            return Regex.Unescape(match.Groups["value"].Value);
        }

        private static bool RequiresApproval(string json)
        {
            return Regex.IsMatch(json ?? string.Empty, "\\\"approval_required\\\"\\s*:\\s*true", RegexOptions.IgnoreCase);
        }

        private static string FirstLine(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return string.Empty;
            }
            var normalized = value.Replace("\r\n", "\n").Replace('\r', '\n');
            var index = normalized.IndexOf('\n');
            return index < 0 ? normalized.Trim() : normalized.Substring(0, index).Trim();
        }
    }
}
