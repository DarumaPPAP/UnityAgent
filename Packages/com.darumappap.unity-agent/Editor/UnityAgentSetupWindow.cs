using System.IO;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    internal sealed class UnityAgentSetupWindow : EditorWindow
    {
        private string hostCommand = "unity-agent";
        private string expectedPlanId = string.Empty;
        private string approvalRef = string.Empty;
        private string output = "UnityAgent Control Plane is ready.";
        private string error = string.Empty;

        [MenuItem("UnityAgent/Setup")]
        private static void Open()
        {
            GetWindow<UnityAgentSetupWindow>("UnityAgent Setup");
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("UnityAgent Setup", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "このUIはEntry Layerです。Official Unity CLIやUnityArtistCLIを直接実行せず、UnityAgent Control Planeだけを呼び出します。",
                MessageType.Info);
            hostCommand = EditorGUILayout.TextField("Control Plane command", hostCommand);
            expectedPlanId = EditorGUILayout.TextField("Expected plan id", expectedPlanId);
            approvalRef = EditorGUILayout.TextField("Approval reference", approvalRef);

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Doctor"))
                {
                    Run("doctor");
                }
                if (GUILayout.Button("Plan"))
                {
                    Run("plan");
                }
                using (new EditorGUI.DisabledScope(string.IsNullOrEmpty(expectedPlanId) || string.IsNullOrEmpty(approvalRef)))
                {
                    if (GUILayout.Button("Apply"))
                    {
                        Run("apply");
                    }
                }
            }

            if (!string.IsNullOrEmpty(error))
            {
                EditorGUILayout.HelpBox(error, MessageType.Error);
            }
            EditorGUILayout.LabelField("Control Plane response", EditorStyles.boldLabel);
            EditorGUILayout.TextArea(output, GUILayout.MinHeight(180));
        }

        private void Run(string operation)
        {
            error = string.Empty;
            var projectPath = Directory.GetParent(Application.dataPath).FullName;
            if (!UnityAgentControlPlaneClient.TryRun(
                    operation,
                    projectPath,
                    hostCommand,
                    expectedPlanId,
                    approvalRef,
                    out output,
                    out error))
            {
                Repaint();
                return;
            }
            Repaint();
        }
    }
}
