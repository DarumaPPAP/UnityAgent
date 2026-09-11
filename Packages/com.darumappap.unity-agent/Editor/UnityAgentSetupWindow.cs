using System;
using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    internal sealed class UnityAgentSetupWindow : EditorWindow
    {
        private const string CODEX_PLUGIN_SOURCE = "DarumaPPAP/UnityAgent@v0.0.2-beta";
        private static readonly string[] CODEX_PLUGIN_PRODUCTS = { "unity_agent_codex_plugin" };
        private static readonly string[] ALL_PRODUCTS =
        {
            "official_unity_cli",
            "unity_artist_cli",
            "codex_cli",
            "unity_agent_codex_plugin",
        };

        private string hostCommand = "unity-agent";
        private string output = "UnityAgent Control Plane is ready.";
        private string error = string.Empty;
        private bool showAdvanced;

        [MenuItem("UnityAgent/Setup")]
        private static void Open()
        {
            GetWindow<UnityAgentSetupWindow>("UnityAgent Setup");
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("UnityAgent Setup", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "推奨: Codex PluginはこのWindowから導入します。Unity UIはEntry LayerとしてUnityAgent Control Planeだけを呼び出し、Codex CLIやProviderへ直接接続しません。",
                MessageType.Info);

            EditorGUILayout.Space(6);
            EditorGUILayout.LabelField("Codex Integration", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "Codex CLIを検出し、UnityAgent Pluginの状態確認・Install / RepairをApproval付きSetupとして実行します。",
                MessageType.None);

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Codex Pluginを確認"))
                {
                    Run("doctor", CODEX_PLUGIN_PRODUCTS);
                }
                if (GUILayout.Button("Codex Pluginをインストール / 修復"))
                {
                    InstallCodexPlugin();
                }
            }

            EditorGUILayout.Space(6);
            showAdvanced = EditorGUILayout.Foldout(showAdvanced, "Advanced", true);
            if (showAdvanced)
            {
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

            if (!string.IsNullOrEmpty(error))
            {
                EditorGUILayout.HelpBox(error, MessageType.Error);
            }
            EditorGUILayout.LabelField("Control Plane response", EditorStyles.boldLabel);
            EditorGUILayout.TextArea(output, GUILayout.MinHeight(220));
        }

        private void Run(string operation, string[] products)
        {
            error = string.Empty;
            var projectPath = Directory.GetParent(Application.dataPath).FullName;
            UnityAgentControlPlaneClient.TryRun(
                operation,
                projectPath,
                hostCommand,
                products,
                string.Empty,
                string.Empty,
                string.Empty,
                out output,
                out error);
            Repaint();
        }

        private void InstallCodexPlugin()
        {
            error = string.Empty;
            var projectPath = Directory.GetParent(Application.dataPath).FullName;
            EditorUtility.DisplayProgressBar("UnityAgent Setup", "Codex Plugin setup planを確認しています...", 0.25f);
            try
            {
                if (!UnityAgentControlPlaneClient.TryRun(
                        "plan",
                        projectPath,
                        hostCommand,
                        CODEX_PLUGIN_PRODUCTS,
                        string.Empty,
                        string.Empty,
                        string.Empty,
                        out var planOutput,
                        out var planError))
                {
                    output = planOutput;
                    error = string.IsNullOrEmpty(planError)
                        ? "Codex Plugin setup planを作成できませんでした。Control Plane responseを確認してください。"
                        : planError;
                    Repaint();
                    return;
                }

                output = planOutput;
                var planId = ExtractPlanId(planOutput);
                if (string.IsNullOrEmpty(planId))
                {
                    error = "Control Plane responseからplan_idを取得できませんでした。";
                    Repaint();
                    return;
                }

                if (!RequiresApproval(planOutput))
                {
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
                    if (!UnityAgentControlPlaneClient.TryRun(
                            "apply",
                            projectPath,
                            hostCommand,
                            CODEX_PLUGIN_PRODUCTS,
                            planId,
                            approvalRef,
                            planPath,
                            out output,
                            out error))
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

        private static string ExtractPlanId(string json)
        {
            var match = Regex.Match(json ?? string.Empty, "\\\"plan_id\\\"\\s*:\\s*\\\"(?<value>[^\\\"]+)\\\"");
            return match.Success ? match.Groups["value"].Value : string.Empty;
        }

        private static bool RequiresApproval(string json)
        {
            return Regex.IsMatch(json ?? string.Empty, "\\\"approval_required\\\"\\s*:\\s*true", RegexOptions.IgnoreCase);
        }
    }
}
