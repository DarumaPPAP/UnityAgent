using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace StageLighting
{
    /// <summary>
    /// Scene保存およびLighting更新後にStageLightingDataを同期します。
    /// </summary>
    [InitializeOnLoad]
    internal static class StageLightingDataSynchronizer
    {
        private static bool _synchronizationQueued;

        static StageLightingDataSynchronizer()
        {
            EditorSceneManager.sceneSaved += OnSceneSaved;
            Lightmapping.lightingDataUpdated += QueueLoadedSceneSynchronization;
            Lightmapping.bakeCompleted += QueueLoadedSceneSynchronization;
        }

        internal static bool SynchronizeScene(Scene scene, StageLightingData data)
        {
            if (data == null || !scene.IsValid() || !scene.isLoaded || string.IsNullOrEmpty(scene.path))
            {
                return false;
            }

            bool changed = data.RefreshSceneIdentities();

            if (!data.TryGetEntryByScenePath(scene.path, out StageLightingEntry entry))
            {
                if (changed)
                {
                    EditorUtility.SetDirty(data);
                }

                return changed;
            }

            Scene previousActiveScene = SceneManager.GetActiveScene();
            bool activeSceneChanged = previousActiveScene.handle != scene.handle;

            if (activeSceneChanged && !SceneManager.SetActiveScene(scene))
            {
                if (changed)
                {
                    EditorUtility.SetDirty(data);
                }

                return changed;
            }

            try
            {
                changed |= entry.CaptureEditorState(scene);
                if (changed)
                {
                    EditorUtility.SetDirty(data);
                }

                return changed;
            }
            finally
            {
                if (activeSceneChanged && previousActiveScene.IsValid() && previousActiveScene.isLoaded)
                {
                    SceneManager.SetActiveScene(previousActiveScene);
                }
            }
        }

        internal static bool SynchronizeAllLoadedScenes(StageLightingData data)
        {
            bool changed = false;

            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                changed |= SynchronizeScene(SceneManager.GetSceneAt(i), data);
            }

            return changed;
        }

        private static void OnSceneSaved(Scene scene)
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return;
            }

            if (Lightmapping.isRunning)
            {
                QueueLoadedSceneSynchronization();
                return;
            }

            if (SynchronizeSceneAgainstAllData(scene))
            {
                AssetDatabase.SaveAssets();
            }
        }

        private static void QueueLoadedSceneSynchronization()
        {
            if (_synchronizationQueued || EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return;
            }

            // GI更新中の連続通知をEditorの次回更新へまとめ、同じデータを何度も保存しません。
            _synchronizationQueued = true;
            EditorApplication.delayCall += SynchronizeQueuedLoadedScenes;
        }

        private static void SynchronizeQueuedLoadedScenes()
        {
            _synchronizationQueued = false;

            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return;
            }

            if (Lightmapping.isRunning)
            {
                QueueLoadedSceneSynchronization();
                return;
            }

            bool changed = false;

            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                changed |= SynchronizeSceneAgainstAllData(SceneManager.GetSceneAt(i));
            }

            if (changed)
            {
                AssetDatabase.SaveAssets();
            }
        }

        private static bool SynchronizeSceneAgainstAllData(Scene scene)
        {
            if (!scene.IsValid() || !scene.isLoaded || string.IsNullOrEmpty(scene.path))
            {
                return false;
            }

            string[] dataGuids = AssetDatabase.FindAssets("t:StageLightingData");
            bool changed = false;

            for (int i = 0; i < dataGuids.Length; i++)
            {
                string assetPath = AssetDatabase.GUIDToAssetPath(dataGuids[i]);
                StageLightingData data = AssetDatabase.LoadAssetAtPath<StageLightingData>(assetPath);
                changed |= SynchronizeScene(scene, data);
            }

            return changed;
        }
    }
}
