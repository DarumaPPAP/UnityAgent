using System;
using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    internal sealed class UnityAgentSetupWindow : EditorWindow
    {
        private const string CHANNEL = "0.0.6-beta";
        private const string CODEX_PLUGIN_SOURCE = "DarumaPPAP/UnityAgent@v0.0.6-beta";
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
        private bool showDiagnostics;
        private bool showAdvanced;
        private Vector2 windowScroll;
        private Vector2 diagnosticsScroll;

        private GUIStyle titleStyle;
        private GUIStyle subtitleStyle;
        private GUIStyle cardTitleStyle;
        private GUIStyle cardSubtitleStyle;
        private GUIStyle badgeStyle;
        private GUIStyle pathStyle;
        private GUIStyle primaryButtonStyle;
        private GUIStyle secondaryButtonStyle;

        [MenuItem("UnityAgent/Setup")]
        private static void Open()
        {
            var window = GetWindow<UnityAgentSetupWindow>("UnityAgent Setup");
            window.minSize = new Vector2(620f, 520f);
        }

        private void OnEnable()
        {
            minSize = new Vector2(620f, 520f);
            RefreshAllPaths();
            UpdateIdleStatus();
        }

        private void OnGUI()
        {
            EnsureStyles();
            windowScroll = EditorGUILayout.BeginScrollView(windowScroll);
            DrawHeader();
            EditorGUILayout.Space(10);
            DrawOverview();
            EditorGUILayout.Space(10);
            DrawControlPlaneCard();
            EditorGUILayout.Space(8);
            DrawCodexCard();
            EditorGUILayout.Space(8);
            DrawIntegrationCard();
            EditorGUILayout.Space(10);
            DrawStatusCard();
            EditorGUILayout.Space(8);
            DrawDiagnostics();
            EditorGUILayout.Space(8);
            DrawAdvanced();
            EditorGUILayout.Space(16);
            EditorGUILayout.EndScrollView();
        }

        private void EnsureStyles()
        {
            if (titleStyle != null)
            {
                return;
            }

            titleStyle = new GUIStyle(EditorStyles.boldLabel)
            {
                fontSize = 20,
                fontStyle = FontStyle.Bold,
            };
            subtitleStyle = new GUIStyle(EditorStyles.label)
            {
                fontSize = 11,
                wordWrap = true,
                normal = { textColor = EditorGUIUtility.isProSkin ? new Color(0.72f, 0.74f, 0.78f) : new Color(0.28f, 0.30f, 0.34f) },
            };
            cardTitleStyle = new GUIStyle(EditorStyles.boldLabel)
            {
                fontSize = 13,
                fontStyle = FontStyle.Bold,
            };
            cardSubtitleStyle = new GUIStyle(EditorStyles.label)
            {
                fontSize = 10,
                wordWrap = true,
                normal = { textColor = EditorGUIUtility.isProSkin ? new Color(0.68f, 0.70f, 0.74f) : new Color(0.34f, 0.36f, 0.40f) },
            };
            badgeStyle = new GUIStyle(EditorStyles.miniBoldLabel)
            {
                alignment = TextAnchor.MiddleRight,
            };
            pathStyle = new GUIStyle(EditorStyles.textField)
            {
                fontSize = 10,
            };
            primaryButtonStyle = new GUIStyle(GUI.skin.button)
            {
                fixedHeight = 32f,
                fontStyle = FontStyle.Bold,
            };
            secondaryButtonStyle = new GUIStyle(GUI.skin.button)
            {
                fixedHeight = 25f,
            };
        }

        private void DrawHeader()
        {
            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUILayout.VerticalScope())
                {
                    EditorGUILayout.LabelField("UnityAgent Setup", titleStyle);
                    EditorGUILayout.LabelField(
                        "Control PlaneとCodexを1つの画面で検出・導入・診断します。通常のMutationはControl Plane経由、Control Plane未導入時だけBootstrapを使用します。",
                        subtitleStyle);
                }
                GUILayout.FlexibleSpace();
                var versionStyle = new GUIStyle(EditorStyles.miniBoldLabel)
                {
                    alignment = TextAnchor.UpperRight,
                    normal = { textColor = EditorGUIUtility.isProSkin ? new Color(0.55f, 0.75f, 1f) : new Color(0.12f, 0.38f, 0.72f) },
                };
                GUILayout.Label("v" + CHANNEL + "\nBETA", versionStyle, GUILayout.Width(90f));
            }
        }

        private void DrawOverview()
        {
            var controlPlaneReady = !string.IsNullOrWhiteSpace(controlPlanePath);
            var codexReady = !string.IsNullOrWhiteSpace(codexCliPath);
            var readyCount = (controlPlaneReady ? 1 : 0) + (codexReady ? 1 : 0);

            BeginCard();
            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUILayout.VerticalScope())
                {
                    EditorGUILayout.LabelField("Setup Readiness", cardTitleStyle);
                    EditorGUILayout.LabelField(
                        controlPlaneReady && codexReady
                            ? "Core dependencies are ready. Codex Pluginの状態確認・Installへ進めます。"
                            : "不足している依存を上から順に解決してください。",
                        cardSubtitleStyle);
                }
                GUILayout.FlexibleSpace();
                DrawBadge(readyCount + "/2 READY", readyCount == 2 ? ReadyColor : ActionColor);
            }

            EditorGUILayout.Space(6);
            var rect = EditorGUILayout.GetControlRect(false, 6f);
            var background = rect;
            background.height = 4f;
            EditorGUI.DrawRect(background, EditorGUIUtility.isProSkin ? new Color(0.16f, 0.17f, 0.19f) : new Color(0.82f, 0.83f, 0.85f));
            if (readyCount > 0)
            {
                var progress = background;
                progress.width *= readyCount / 2f;
                EditorGUI.DrawRect(progress, ReadyColor);
            }
            EndCard();
        }

        private void DrawControlPlaneCard()
        {
            var ready = !string.IsNullOrWhiteSpace(controlPlanePath);
            var running = UnityAgentControlPlaneBootstrap.IsRunning;

            BeginCard();
            DrawCardHeader(
                "1. UnityAgent Control Plane",
                "UnityAgentのPlan / Approval / Provider routing / Evidenceを担当する実行基盤です。",
                running ? "INSTALLING" : (ready ? "READY" : "ACTION REQUIRED"),
                running ? BusyColor : (ready ? ReadyColor : ActionColor));

            EditorGUILayout.Space(6);
            DrawResolvedPath(controlPlanePath, controlPlanePathSource);

            using (new EditorGUILayout.HorizontalScope())
            {
                if (!ready)
                {
                    using (new EditorGUI.DisabledScope(running))
                    {
                        var previous = GUI.backgroundColor;
                        GUI.backgroundColor = new Color(0.30f, 0.58f, 0.95f);
                        if (GUILayout.Button(running ? "Control Planeをインストール中..." : "Install Control Plane", primaryButtonStyle))
                        {
                            InstallControlPlaneBootstrap();
                        }
                        GUI.backgroundColor = previous;
                    }
                }
                else
                {
                    GUILayout.Label("Control Plane detected", cardSubtitleStyle);
                    GUILayout.FlexibleSpace();
                }
            }

            EditorGUILayout.Space(4);
            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUI.DisabledScope(running))
                {
                    if (GUILayout.Button("再検出", secondaryButtonStyle, GUILayout.Width(82f)))
                    {
                        RefreshControlPlanePath(true);
                        UpdateIdleStatus();
                    }
                    if (GUILayout.Button("参照...", secondaryButtonStyle, GUILayout.Width(82f)))
                    {
                        BrowseControlPlane();
                    }
                    if (UnityAgentControlPlanePathResolver.HasOverride && GUILayout.Button("Override解除", secondaryButtonStyle, GUILayout.Width(110f)))
                    {
                        UnityAgentControlPlanePathResolver.ClearOverride();
                        RefreshControlPlanePath(false);
                        UpdateIdleStatus();
                    }
                }
            }

            if (!ready && !running && !string.IsNullOrWhiteSpace(controlPlanePathDiagnostic))
            {
                DrawHint(controlPlanePathDiagnostic, ActionColor);
            }
            EndCard();
        }

        private void DrawCodexCard()
        {
            var ready = !string.IsNullOrWhiteSpace(codexCliPath);
            BeginCard();
            DrawCardHeader(
                "2. Codex CLI",
                "Codex Pluginの確認・導入に使用します。PATHだけでなくnpm / NVM / common locationsも探索します。",
                ready ? "READY" : "OPTIONAL / NOT FOUND",
                ready ? ReadyColor : WarningColor);

            EditorGUILayout.Space(6);
            DrawResolvedPath(codexCliPath, codexPathSource);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("再検出", secondaryButtonStyle, GUILayout.Width(82f)))
                {
                    RefreshCodexPath(true);
                    UpdateIdleStatus();
                }
                if (GUILayout.Button("参照...", secondaryButtonStyle, GUILayout.Width(82f)))
                {
                    BrowseCodex();
                }
                if (UnityAgentCodexPathResolver.HasOverride && GUILayout.Button("Override解除", secondaryButtonStyle, GUILayout.Width(110f)))
                {
                    UnityAgentCodexPathResolver.ClearOverride();
                    RefreshCodexPath(false);
                    UpdateIdleStatus();
                }
            }
            if (!ready && !string.IsNullOrWhiteSpace(codexPathDiagnostic))
            {
                DrawHint(codexPathDiagnostic, WarningColor);
            }
            EndCard();
        }

        private void DrawIntegrationCard()
        {
            var controlPlaneReady = !string.IsNullOrWhiteSpace(controlPlanePath);
            var codexReady = !string.IsNullOrWhiteSpace(codexCliPath);
            BeginCard();
            DrawCardHeader(
                "3. Codex Integration",
                "Plugin mutationは必ず Control Plane → Installer Provider を通り、InstallReceipt / Evidenceを残します。",
                controlPlaneReady && codexReady ? "READY TO CHECK" : "WAITING",
                controlPlaneReady && codexReady ? ReadyColor : MutedColor);

            EditorGUILayout.Space(8);
            using (new EditorGUI.DisabledScope(!controlPlaneReady || UnityAgentControlPlaneBootstrap.IsRunning))
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("状態を確認", secondaryButtonStyle))
                {
                    Run("doctor", CODEX_INTEGRATION_PRODUCTS);
                }
                using (new EditorGUI.DisabledScope(!codexReady))
                {
                    var previous = GUI.backgroundColor;
                    GUI.backgroundColor = codexReady ? new Color(0.30f, 0.58f, 0.95f) : previous;
                    if (GUILayout.Button("Codex Pluginをインストール / 修復", primaryButtonStyle))
                    {
                        InstallCodexPlugin();
                    }
                    GUI.backgroundColor = previous;
                }
            }

            if (!controlPlaneReady)
            {
                DrawHint("先にControl Planeをインストールしてください。", ActionColor);
            }
            else if (!codexReady)
            {
                DrawHint("Codex Pluginを使う場合はCodex CLIを検出または指定してください。", WarningColor);
            }
            EndCard();
        }

        private void DrawStatusCard()
        {
            BeginCard();
            DrawCardHeader("Current Status", "直近のSetup / Bootstrap結果", "STATUS", ResolveStatusColor());
            EditorGUILayout.Space(5);
            EditorGUILayout.HelpBox(statusMessage, statusType);
            if (!string.IsNullOrWhiteSpace(error))
            {
                using (new EditorGUILayout.HorizontalScope())
                {
                    GUILayout.FlexibleSpace();
                    if (GUILayout.Button("エラーをコピー", secondaryButtonStyle, GUILayout.Width(120f)))
                    {
                        EditorGUIUtility.systemCopyBuffer = error;
                    }
                }
            }
            EndCard();
        }

        private void DrawDiagnostics()
        {
            showDiagnostics = EditorGUILayout.Foldout(showDiagnostics, "Diagnostics / Raw response", true);
            if (!showDiagnostics)
            {
                return;
            }

            BeginCard();
            diagnosticsScroll = EditorGUILayout.BeginScrollView(diagnosticsScroll, GUILayout.MinHeight(180f), GUILayout.MaxHeight(320f));
            EditorGUILayout.TextArea(BuildRawLog(), GUILayout.ExpandHeight(true));
            EditorGUILayout.EndScrollView();
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("ログをコピー", secondaryButtonStyle))
                {
                    EditorGUIUtility.systemCopyBuffer = BuildRawLog();
                }
                if (GUILayout.Button("クリア", secondaryButtonStyle, GUILayout.Width(90f)))
                {
                    output = string.Empty;
                    error = string.Empty;
                    UpdateIdleStatus();
                }
            }
            EndCard();
        }

        private void DrawAdvanced()
        {
            showAdvanced = EditorGUILayout.Foldout(showAdvanced, "Advanced", true);
            if (!showAdvanced)
            {
                return;
            }

            BeginCard();
            using (new EditorGUI.DisabledScope(string.IsNullOrWhiteSpace(controlPlanePath)))
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("全Toolchain Doctor", secondaryButtonStyle))
                {
                    Run("doctor", ALL_PRODUCTS);
                }
                if (GUILayout.Button("全Toolchain Plan", secondaryButtonStyle))
                {
                    Run("plan", ALL_PRODUCTS);
                }
            }
            EditorGUILayout.Space(4);
            EditorGUILayout.LabelField("Bootstrap channel: v" + UnityAgentControlPlaneBootstrap.Channel, cardSubtitleStyle);
            EndCard();
        }

        private void InstallControlPlaneBootstrap()
        {
            if (!EditorUtility.DisplayDialog(
                    "Install UnityAgent Control Plane",
                    "UnityAgent Control Plane v" + CHANNEL + " をユーザースコープへインストールします。\n\n" +
                    "BootstrapはControl Plane本体だけを導入します。Codex PluginやProviderは直接変更しません。\n" +
                    "Release wheelはSHA-256検証後にpip --userでインストールされます。",
                    "インストール",
                    "キャンセル"))
            {
                return;
            }

            statusMessage = "Control Planeをインストールしています...";
            statusType = MessageType.Info;
            output = string.Empty;
            error = string.Empty;
            Repaint();

            if (!UnityAgentControlPlaneBootstrap.Start(OnBootstrapCompleted, out var bootstrapError))
            {
                SetError(bootstrapError);
            }
        }

        private void OnBootstrapCompleted(UnityAgentControlPlaneBootstrap.Result result)
        {
            output = result.Output ?? string.Empty;
            error = result.Error ?? string.Empty;
            RefreshControlPlanePath(false);

            if (result.Success && !string.IsNullOrWhiteSpace(controlPlanePath))
            {
                statusMessage = "Control Planeのインストールが完了しました。Codex Integrationへ進めます。";
                statusType = MessageType.Info;
            }
            else
            {
                statusMessage = "Control Plane Bootstrapに失敗しました。Diagnosticsを確認してください。";
                statusType = MessageType.Error;
                showDiagnostics = true;
                if (string.IsNullOrWhiteSpace(error))
                {
                    error = "Bootstrap ExitCode=" + result.ExitCode + "。インストール後のControl Planeを解決できませんでした。";
                }
            }
            Repaint();
        }

        private void DrawResolvedPath(string path, string source)
        {
            using (new EditorGUI.DisabledScope(true))
            {
                EditorGUILayout.TextField("Resolved Path", string.IsNullOrWhiteSpace(path) ? "Not Found" : path, pathStyle);
            }
            EditorGUILayout.LabelField("Source: " + (string.IsNullOrWhiteSpace(source) ? "-" : source), cardSubtitleStyle);
        }

        private void DrawCardHeader(string title, string subtitle, string badge, Color color)
        {
            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUILayout.VerticalScope())
                {
                    EditorGUILayout.LabelField(title, cardTitleStyle);
                    EditorGUILayout.LabelField(subtitle, cardSubtitleStyle);
                }
                GUILayout.FlexibleSpace();
                DrawBadge(badge, color);
            }
        }

        private void DrawBadge(string text, Color color)
        {
            var style = new GUIStyle(badgeStyle) { normal = { textColor = color } };
            GUILayout.Label(text, style, GUILayout.Width(120f));
        }

        private void DrawHint(string message, Color color)
        {
            var rect = EditorGUILayout.GetControlRect(false, 24f);
            EditorGUI.DrawRect(new Rect(rect.x, rect.y + 4f, 3f, 16f), color);
            var labelRect = new Rect(rect.x + 10f, rect.y, rect.width - 10f, rect.height);
            GUI.Label(labelRect, message, cardSubtitleStyle);
        }

        private static void BeginCard()
        {
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
        }

        private static void EndCard()
        {
            EditorGUILayout.EndVertical();
        }

        private void RefreshAllPaths()
        {
            RefreshControlPlanePath(false);
            RefreshCodexPath(false);
        }

        private void RefreshControlPlanePath(bool clearOverride)
        {
            if (clearOverride && UnityAgentControlPlanePathResolver.HasOverride)
            {
                UnityAgentControlPlanePathResolver.ClearOverride();
            }
            controlPlanePath = UnityAgentControlPlanePathResolver.Resolve(
                out controlPlanePathSource,
                out controlPlanePathDiagnostic) ?? string.Empty;
            Repaint();
        }

        private void RefreshCodexPath(bool clearOverride)
        {
            if (clearOverride && UnityAgentCodexPathResolver.HasOverride)
            {
                UnityAgentCodexPathResolver.ClearOverride();
            }
            codexCliPath = UnityAgentCodexPathResolver.Resolve(out codexPathSource, out codexPathDiagnostic) ?? string.Empty;
            Repaint();
        }

        private void UpdateIdleStatus()
        {
            if (UnityAgentControlPlaneBootstrap.IsRunning)
            {
                statusMessage = "Control Planeをインストールしています...";
                statusType = MessageType.Info;
                return;
            }
            if (string.IsNullOrWhiteSpace(controlPlanePath))
            {
                statusMessage = "Control Planeは未導入です。『Install Control Plane』からこのWindow内でセットアップできます。";
                statusType = MessageType.Warning;
                return;
            }
            if (string.IsNullOrWhiteSpace(codexCliPath))
            {
                statusMessage = "Control PlaneはReadyです。Codex Pluginを利用する場合はCodex CLIを検出または指定してください。";
                statusType = MessageType.Warning;
                return;
            }
            statusMessage = "Control Plane / Codex CLIはReadyです。Codex Pluginの状態確認またはInstallへ進めます。";
            statusType = MessageType.Info;
        }

        private void BrowseControlPlane()
        {
            var selected = EditorUtility.OpenFilePanel("UnityAgent Control Planeを選択", SafeDirectory(controlPlanePath), string.Empty);
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
            RefreshControlPlanePath(false);
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
            RefreshCodexPath(false);
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
                SetError("UnityAgent Control Planeが必要です。先にInstall Control Planeを実行してください。");
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
            showDiagnostics |= !success;
            Repaint();
        }

        private void InstallCodexPlugin()
        {
            error = string.Empty;
            EnsurePathsBeforeRequest();
            if (string.IsNullOrWhiteSpace(controlPlanePath))
            {
                SetError("UnityAgent Control Planeが必要です。先にInstall Control Planeを実行してください。");
                return;
            }
            if (string.IsNullOrWhiteSpace(codexCliPath))
            {
                statusMessage = "Codex CLIが必要です。Codex CLIカードから再検出またはPath指定を行ってください。";
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
                    showDiagnostics = true;
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
                    EditorUtility.DisplayProgressBar("UnityAgent Setup", "Codex Pluginをインストールしています...", 0.72f);
                    var applySuccess = UnityAgentControlPlaneClient.TryRun(
                        "apply", projectPath, controlPlanePath, CODEX_INTEGRATION_PRODUCTS,
                        planId, approvalRef, planPath, codexCliPath,
                        out output, out error);
                    statusMessage = BuildReadableMessage(applySuccess, output, error);
                    statusType = ResolveMessageType(applySuccess, output, error);
                    showDiagnostics |= !applySuccess;
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
                RefreshControlPlanePath(false);
            }
            if (string.IsNullOrWhiteSpace(codexCliPath) || !File.Exists(codexCliPath))
            {
                RefreshCodexPath(false);
            }
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
                raw += "[stdout / Control Plane or Bootstrap]\n" + output.Trim();
            }
            return string.IsNullOrWhiteSpace(raw) ? "ログはありません。" : raw;
        }

        private void SetError(string message)
        {
            error = message ?? "Unknown error";
            statusMessage = error;
            statusType = MessageType.Error;
            showDiagnostics = true;
            Repaint();
        }

        private static string BuildReadableMessage(bool success, string json, string processError)
        {
            var combined = (json ?? string.Empty) + "\n" + (processError ?? string.Empty);
            if (combined.IndexOf("codex_cli_override_missing", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "指定したCodex CLI Pathが存在しません。Pathを選び直すかOverrideを解除してください。";
            }
            if (combined.IndexOf("codex_cli_unavailable", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "Codex CLIを検出できません。Codex CLIカードから再検出またはPath指定を行ってください。";
            }
            if (combined.IndexOf("codex_cli_execution_failed", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "Codex CLIは見つかりましたが実行確認に失敗しました。Diagnosticsを確認してください。";
            }
            if (combined.IndexOf("plugin_not_installed", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "Codex CLIはReadyです。UnityAgent Codex Pluginは未導入です。Install / Repairを実行してください。";
            }
            if (combined.IndexOf("plugin_not_enabled", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "UnityAgent Codex Pluginは存在しますが無効です。Install / Repairを実行してください。";
            }
            if (combined.IndexOf("plugin_version_mismatch", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "UnityAgent Codex PluginのVersionが現在のUnityAgentと一致しません。Install / Repairを実行してください。";
            }
            if (combined.IndexOf("marketplace name 'unity-agent' is already owned", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "Codex Marketplace名 'unity-agent' が別Sourceに使われています。安全のため自動上書きを停止しました。";
            }
            if (!success)
            {
                return string.IsNullOrWhiteSpace(processError)
                    ? "UnityAgent setupに失敗しました。Diagnosticsを確認してください。"
                    : FirstLine(processError);
            }
            if (Regex.IsMatch(json ?? string.Empty, "\\\"approval_required\\\"\\s*:\\s*true", RegexOptions.IgnoreCase))
            {
                return "環境確認が完了しました。Codex Pluginのインストールには承認が必要です。";
            }
            if (combined.IndexOf("unity-agent@unity-agent", StringComparison.OrdinalIgnoreCase) >= 0 ||
                combined.IndexOf("\"status\": \"completed\"", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "UnityAgent setupが完了しました。";
            }
            return "処理が完了しました。";
        }

        private static MessageType ResolveMessageType(bool success, string json, string processError)
        {
            if (!success)
            {
                return MessageType.Error;
            }
            var combined = (json ?? string.Empty) + "\n" + (processError ?? string.Empty);
            return combined.IndexOf("unavailable", StringComparison.OrdinalIgnoreCase) >= 0
                ? MessageType.Warning
                : MessageType.Info;
        }

        private static string ExtractJsonString(string json, string key)
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return string.Empty;
            }
            var match = Regex.Match(json, "\\\"" + Regex.Escape(key) + "\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"");
            return match.Success ? match.Groups[1].Value : string.Empty;
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
            var lines = value.Trim().Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            return lines.Length == 0 ? value.Trim() : lines[0];
        }

        private Color ResolveStatusColor()
        {
            switch (statusType)
            {
                case MessageType.Error: return ErrorColor;
                case MessageType.Warning: return WarningColor;
                default: return ReadyColor;
            }
        }

        private static Color ReadyColor => EditorGUIUtility.isProSkin ? new Color(0.38f, 0.86f, 0.58f) : new Color(0.05f, 0.50f, 0.22f);
        private static Color WarningColor => EditorGUIUtility.isProSkin ? new Color(1.0f, 0.72f, 0.28f) : new Color(0.72f, 0.42f, 0.02f);
        private static Color ActionColor => EditorGUIUtility.isProSkin ? new Color(0.42f, 0.68f, 1.0f) : new Color(0.08f, 0.38f, 0.78f);
        private static Color BusyColor => EditorGUIUtility.isProSkin ? new Color(0.70f, 0.58f, 1.0f) : new Color(0.42f, 0.24f, 0.74f);
        private static Color ErrorColor => EditorGUIUtility.isProSkin ? new Color(1.0f, 0.42f, 0.42f) : new Color(0.72f, 0.08f, 0.08f);
        private static Color MutedColor => EditorGUIUtility.isProSkin ? new Color(0.62f, 0.64f, 0.68f) : new Color(0.40f, 0.42f, 0.46f);
    }
}
