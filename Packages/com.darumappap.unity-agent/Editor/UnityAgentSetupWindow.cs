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
        private const string SETUP_LOGO_ASSET_GUID = "3238c045646b49f9b00513e4f21cfee1";
        private const string SETUP_LOGO_ASSET_PATH = "Packages/com.darumappap.unity-agent/Editor/Resources/UnityAgentSetupLogo.png";
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
        private Texture2D setupLogoTexture;

        private GUIStyle titleStyle;
        private GUIStyle subtitleStyle;
        private GUIStyle cardTitleStyle;
        private GUIStyle cardSubtitleStyle;
        private GUIStyle badgeStyle;
        private GUIStyle pathStyle;
        private GUIStyle primaryButtonStyle;
        private GUIStyle secondaryButtonStyle;
        private GUIStyle heroSubtitleStyle;
        private GUIStyle heroVersionStyle;
        private GUIStyle cardStyle;
        private GUIStyle fieldLabelStyle;

        [MenuItem("UnityAgent/Setup")]
        private static void Open()
        {
            var window = GetWindow<UnityAgentSetupWindow>("UnityAgent Setup");
            window.minSize = new Vector2(700f, 540f);
        }

        private void OnEnable()
        {
            minSize = new Vector2(700f, 540f);
            setupLogoTexture = LoadSetupLogoTexture();
            EditorApplication.delayCall += RetrySetupLogoLoad;
            RefreshAllPaths();
            UpdateIdleStatus();
        }

        private void OnFocus()
        {
            RetrySetupLogoLoad();
        }

        private void RetrySetupLogoLoad()
        {
            if (setupLogoTexture != null)
            {
                return;
            }

            setupLogoTexture = LoadSetupLogoTexture();
            if (setupLogoTexture != null)
            {
                Repaint();
            }
        }

        private static Texture2D LoadSetupLogoTexture()
        {
            var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(SETUP_LOGO_ASSET_PATH);
            if (texture != null)
            {
                return texture;
            }

            var assetPath = AssetDatabase.GUIDToAssetPath(SETUP_LOGO_ASSET_GUID);
            if (string.IsNullOrWhiteSpace(assetPath))
            {
                return null;
            }

            return AssetDatabase.LoadAssetAtPath<Texture2D>(assetPath);
        }

        private void OnGUI()
        {
            EnsureStyles();
            windowScroll = EditorGUILayout.BeginScrollView(windowScroll);
            EditorGUILayout.Space(4);

            using (new EditorGUILayout.HorizontalScope())
            {
                GUILayout.Space(8f);
                using (new EditorGUILayout.VerticalScope())
                {
                    DrawHeader();
                    EditorGUILayout.Space(12);
                    DrawOverview();
                    EditorGUILayout.Space(10);
                    DrawControlPlaneCard();
                    EditorGUILayout.Space(10);
                    DrawCodexCard();
                    EditorGUILayout.Space(10);
                    DrawIntegrationCard();
                    EditorGUILayout.Space(10);
                    DrawStatusCard();
                    EditorGUILayout.Space(10);
                    DrawDiagnostics();
                    EditorGUILayout.Space(8);
                    DrawAdvanced();
                    EditorGUILayout.Space(16);
                }
                GUILayout.Space(8f);
            }

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
                alignment = TextAnchor.MiddleCenter,
                fontSize = 30,
                fontStyle = FontStyle.Bold,
            };
            titleStyle.normal.textColor = EditorGUIUtility.isProSkin
                ? new Color(0.96f, 0.96f, 0.97f)
                : new Color(0.08f, 0.08f, 0.09f);

            subtitleStyle = new GUIStyle(EditorStyles.label)
            {
                fontSize = 11,
                wordWrap = true,
            };
            subtitleStyle.normal.textColor = EditorGUIUtility.isProSkin
                ? new Color(0.78f, 0.80f, 0.83f)
                : new Color(0.25f, 0.27f, 0.30f);

            cardTitleStyle = new GUIStyle(EditorStyles.boldLabel)
            {
                fontSize = 16,
                fontStyle = FontStyle.Bold,
            };
            cardTitleStyle.normal.textColor = EditorGUIUtility.isProSkin
                ? new Color(0.94f, 0.95f, 0.97f)
                : new Color(0.12f, 0.13f, 0.15f);

            cardSubtitleStyle = new GUIStyle(EditorStyles.label)
            {
                fontSize = 11,
                wordWrap = true,
            };
            cardSubtitleStyle.normal.textColor = EditorGUIUtility.isProSkin
                ? new Color(0.70f, 0.73f, 0.78f)
                : new Color(0.32f, 0.34f, 0.38f);

            badgeStyle = new GUIStyle(EditorStyles.miniBoldLabel)
            {
                alignment = TextAnchor.MiddleRight,
                fontSize = 11,
                fontStyle = FontStyle.Bold,
            };

            pathStyle = new GUIStyle(EditorStyles.textField)
            {
                fontSize = 11,
                fixedHeight = 24f,
            };

            primaryButtonStyle = new GUIStyle(GUI.skin.button)
            {
                fixedHeight = 36f,
                fontSize = 12,
                fontStyle = FontStyle.Bold,
            };

            secondaryButtonStyle = new GUIStyle(GUI.skin.button)
            {
                fixedHeight = 30f,
                fontSize = 11,
            };

            heroSubtitleStyle = new GUIStyle(EditorStyles.miniBoldLabel)
            {
                alignment = TextAnchor.MiddleCenter,
                fontSize = 11,
                fontStyle = FontStyle.Bold,
            };
            heroSubtitleStyle.normal.textColor = EditorGUIUtility.isProSkin
                ? new Color(0.74f, 0.76f, 0.80f)
                : new Color(0.24f, 0.24f, 0.26f);

            heroVersionStyle = new GUIStyle(EditorStyles.miniBoldLabel)
            {
                alignment = TextAnchor.MiddleRight,
                fontSize = 10,
                fontStyle = FontStyle.Bold,
            };
            heroVersionStyle.normal.textColor = BrandRed;

            cardStyle = new GUIStyle(EditorStyles.helpBox)
            {
                padding = new RectOffset(14, 14, 12, 12),
                margin = new RectOffset(0, 0, 0, 0),
            };

            fieldLabelStyle = new GUIStyle(EditorStyles.miniLabel)
            {
                alignment = TextAnchor.MiddleLeft,
                fontSize = 11,
            };
            fieldLabelStyle.normal.textColor = EditorGUIUtility.isProSkin
                ? new Color(0.72f, 0.74f, 0.78f)
                : new Color(0.34f, 0.36f, 0.40f);
        }

        private void DrawHeader()
        {
            var heroRect = GUILayoutUtility.GetRect(0f, 178f, GUILayout.ExpandWidth(true));
            EditorGUI.DrawRect(heroRect, HeroBackgroundColor);

            EditorGUI.DrawRect(
                new Rect(heroRect.x, heroRect.y, heroRect.width, 4f),
                BrandRed);
            EditorGUI.DrawRect(
                new Rect(heroRect.x + 12f, heroRect.yMax - 1f, heroRect.width - 24f, 1f),
                HeroDividerColor);

            var logoTexture = setupLogoTexture ?? LoadSetupLogoTexture();
            var logoSlot = new Rect(
                heroRect.x + 38f,
                heroRect.y + 16f,
                Mathf.Max(0f, heroRect.width - 76f),
                116f);

            if (logoTexture != null)
            {
                setupLogoTexture = logoTexture;
                GUI.DrawTexture(logoSlot, logoTexture, ScaleMode.ScaleToFit, true);
            }
            else
            {
                GUI.Label(logoSlot, "UNITYAGENT", titleStyle);
            }

            GUI.Label(
                new Rect(heroRect.x + 40f, heroRect.y + 132f, heroRect.width - 80f, 22f),
                "SETUP  /  CONTROL PLANE  /  CODEX",
                heroSubtitleStyle);

            GUI.Label(
                new Rect(heroRect.xMax - 190f, heroRect.yMax - 27f, 174f, 18f),
                "v" + CHANNEL + "  BETA",
                heroVersionStyle);
        }

        private void DrawOverview()
        {
            var controlPlaneReady = !string.IsNullOrWhiteSpace(controlPlanePath);
            var codexReady = !string.IsNullOrWhiteSpace(codexCliPath);
            var readyCount = (controlPlaneReady ? 1 : 0) + (codexReady ? 1 : 0);

            BeginCard();
            DrawCardHeader(
                "Setup Readiness",
                controlPlaneReady && codexReady
                    ? "Core dependencies are ready. Codex Pluginの状態確認・Installへ進めます。"
                    : "不足している依存を上から順に解決してください。",
                readyCount + "/2 READY",
                readyCount == 2 ? ReadyColor : ActionColor);

            EditorGUILayout.Space(4);
            var rect = EditorGUILayout.GetControlRect(false, 7f);
            var background = new Rect(rect.x + 2f, rect.y + 1f, rect.width - 4f, 5f);
            EditorGUI.DrawRect(background, ProgressBackgroundColor);
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
                        GUI.backgroundColor = BrandRed;
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
                    GUI.backgroundColor = codexReady ? BrandRed : previous;
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
            var displayPath = string.IsNullOrWhiteSpace(path) ? "Not Found" : path;

            using (new EditorGUILayout.HorizontalScope())
            {
                GUILayout.Label("Resolved Path", fieldLabelStyle, GUILayout.Width(112f));
                using (new EditorGUI.DisabledScope(true))
                {
                    EditorGUILayout.TextField(displayPath, pathStyle);
                }
                using (new EditorGUI.DisabledScope(string.IsNullOrWhiteSpace(path)))
                {
                    if (GUILayout.Button("Copy", GUILayout.Width(52f), GUILayout.Height(24f)))
                    {
                        EditorGUIUtility.systemCopyBuffer = path;
                    }
                }
            }

            EditorGUILayout.Space(3f);
            using (new EditorGUILayout.HorizontalScope())
            {
                GUILayout.Label("Source", fieldLabelStyle, GUILayout.Width(112f));
                GUILayout.Label(string.IsNullOrWhiteSpace(source) ? "-" : source, cardSubtitleStyle);
            }
        }

        private void DrawCardHeader(string title, string subtitle, string badge, Color color)
        {
            var rect = GUILayoutUtility.GetRect(0f, 54f, GUILayout.ExpandWidth(true));

            EditorGUI.DrawRect(
                new Rect(rect.x, rect.y + 5f, 4f, rect.height - 10f),
                BrandRed);
            EditorGUI.DrawRect(
                new Rect(rect.x + 10f, rect.y, rect.width - 10f, 1f),
                CardTopLineColor);

            var textWidth = Mathf.Max(120f, rect.width - 178f);
            GUI.Label(
                new Rect(rect.x + 14f, rect.y + 4f, textWidth, 24f),
                title,
                cardTitleStyle);
            GUI.Label(
                new Rect(rect.x + 14f, rect.y + 28f, textWidth, 22f),
                subtitle,
                cardSubtitleStyle);

            var style = new GUIStyle(badgeStyle) { normal = { textColor = color } };
            GUI.Label(
                new Rect(rect.xMax - 158f, rect.y + 5f, 148f, 22f),
                badge,
                style);
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

        private void BeginCard()
        {
            EditorGUILayout.BeginVertical(cardStyle);
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

        private static Color HeroBackgroundColor => EditorGUIUtility.isProSkin ? new Color(0.095f, 0.105f, 0.12f) : new Color(0.90f, 0.91f, 0.93f);
        private static Color HeroDividerColor => EditorGUIUtility.isProSkin ? new Color(0.20f, 0.22f, 0.25f) : new Color(0.72f, 0.74f, 0.78f);
        private static Color ProgressBackgroundColor => EditorGUIUtility.isProSkin ? new Color(0.15f, 0.17f, 0.19f) : new Color(0.80f, 0.82f, 0.85f);
        private static Color CardTopLineColor => EditorGUIUtility.isProSkin ? new Color(0.42f, 0.16f, 0.18f) : new Color(0.72f, 0.20f, 0.22f);
        private static Color ReadyColor => EditorGUIUtility.isProSkin ? new Color(0.38f, 0.86f, 0.58f) : new Color(0.05f, 0.50f, 0.22f);
        private static Color WarningColor => EditorGUIUtility.isProSkin ? new Color(1.0f, 0.72f, 0.28f) : new Color(0.72f, 0.42f, 0.02f);
        private static Color BrandRed => EditorGUIUtility.isProSkin ? new Color(0.96f, 0.16f, 0.18f) : new Color(0.80f, 0.06f, 0.08f);
        private static Color ActionColor => BrandRed;
        private static Color BusyColor => EditorGUIUtility.isProSkin ? new Color(0.70f, 0.58f, 1.0f) : new Color(0.42f, 0.24f, 0.74f);
        private static Color ErrorColor => EditorGUIUtility.isProSkin ? new Color(1.0f, 0.42f, 0.42f) : new Color(0.72f, 0.08f, 0.08f);
        private static Color MutedColor => EditorGUIUtility.isProSkin ? new Color(0.62f, 0.64f, 0.68f) : new Color(0.40f, 0.42f, 0.46f);
    }
}
