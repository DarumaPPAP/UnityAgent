using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace StageLighting
{
    /// <summary>
    /// StageLightingDataの同期操作を提供します。
    /// </summary>
    [CustomEditor(typeof(StageLightingData))]
    internal sealed class StageLightingDataEditor : Editor
    {
        public override void OnInspectorGUI()
        {
            StageLightingData data = (StageLightingData)target;

            if (DrawDefaultInspector())
            {
                if (data.RefreshSceneIdentities())
                {
                    EditorUtility.SetDirty(data);
                }
            }

            EditorGUILayout.Space();
            EditorGUILayout.HelpBox(
                "Scene保存時とLighting Bake更新時に、登録済みSceneのEnvironment、Lighting Settings、Lighting Data Assetを自動同期します。",
                MessageType.Info);

            if (GUILayout.Button("アクティブSceneから同期"))
            {
                SynchronizeActiveScene(data);
            }

            if (GUILayout.Button("ロード済みSceneから一括同期"))
            {
                SynchronizeLoadedScenes(data);
            }

            if (GUILayout.Button("DataをアクティブSceneへ適用"))
            {
                ApplyToActiveScene(data);
            }
        }

        private static void SynchronizeActiveScene(StageLightingData data)
        {
            Scene scene = SceneManager.GetActiveScene();

            if (!data.TryGetEntryByScenePath(scene.path, out _))
            {
                EditorUtility.DisplayDialog(
                    "Stage Lighting",
                    "アクティブSceneはStageLightingDataに登録されていません。",
                    "OK");
                return;
            }

            if (StageLightingDataSynchronizer.SynchronizeScene(scene, data))
            {
                AssetDatabase.SaveAssets();
            }
        }

        private static void SynchronizeLoadedScenes(StageLightingData data)
        {
            if (StageLightingDataSynchronizer.SynchronizeAllLoadedScenes(data))
            {
                AssetDatabase.SaveAssets();
            }
        }

        private static void ApplyToActiveScene(StageLightingData data)
        {
            Scene scene = SceneManager.GetActiveScene();

            if (!scene.IsValid() || !scene.isLoaded || string.IsNullOrEmpty(scene.path))
            {
                EditorUtility.DisplayDialog(
                    "Stage Lighting",
                    "保存済みのアクティブSceneを開いてください。",
                    "OK");
                return;
            }

            if (!data.TryGetEntryByScenePath(scene.path, out StageLightingEntry entry))
            {
                EditorUtility.DisplayDialog(
                    "Stage Lighting",
                    "アクティブSceneはStageLightingDataに登録されていません。",
                    "OK");
                return;
            }

            entry.ApplyEditorState(scene);
            DynamicGI.UpdateEnvironment();
            EditorSceneManager.MarkSceneDirty(scene);

            EditorUtility.DisplayDialog(
                "Stage Lighting",
                "DataをSceneへ適用しました。Lighting Data AssetはSceneの再ロード時に反映されるため、Sceneを保存して開き直してください。",
                "OK");
        }
    }
}
