using UnityEngine;
using UnityEngine.SceneManagement;

namespace StageLighting
{
    /// <summary>
    /// Stage Sceneのロードを検知し、登録済みStageのLightingを有効化します。
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class StageLightingExchangeSystem : MonoBehaviour
    {
        [SerializeField] private StageLightingData _stageLightingData;

        private bool _requiresRetetrahedralization;

        private void OnEnable()
        {
            SceneManager.sceneLoaded += OnSceneLoaded;
            LightProbes.needsRetetrahedralization += OnNeedsRetetrahedralization;
        }

        private void Start()
        {
            ApplyAlreadyLoadedStage();
        }

        private void LateUpdate()
        {
            if (!_requiresRetetrahedralization)
            {
                return;
            }

            _requiresRetetrahedralization = false;
            LightProbes.TetrahedralizeAsync();
        }

        private void OnDisable()
        {
            SceneManager.sceneLoaded -= OnSceneLoaded;
            LightProbes.needsRetetrahedralization -= OnNeedsRetetrahedralization;
            _requiresRetetrahedralization = false;
        }

        private void OnSceneLoaded(Scene scene, LoadSceneMode loadSceneMode)
        {
            TryApplyStage(scene);
        }

        private void OnNeedsRetetrahedralization()
        {
            // 複数Sceneの追加ロードで通知が連続しても、同一フレーム内では一度だけ再構築します。
            _requiresRetetrahedralization = true;
        }

        private void ApplyAlreadyLoadedStage()
        {
            Scene activeScene = SceneManager.GetActiveScene();
            if (TryApplyStage(activeScene))
            {
                return;
            }

            for (int i = SceneManager.sceneCount - 1; i >= 0; i--)
            {
                Scene scene = SceneManager.GetSceneAt(i);
                if (scene.handle == activeScene.handle)
                {
                    continue;
                }

                if (TryApplyStage(scene))
                {
                    return;
                }
            }
        }

        private bool TryApplyStage(Scene scene)
        {
            if (_stageLightingData == null || !scene.IsValid() || !scene.isLoaded)
            {
                return false;
            }

            if (!_stageLightingData.TryGetEntry(scene, out StageLightingEntry entry))
            {
                return false;
            }

            // LightingDataAssetはSceneロード時に反映されるため、登録StageをLightingの使用元へ切り替えます。
            if (!SceneManager.SetActiveScene(scene))
            {
                Debug.LogError($"[StageLighting] Active Sceneへの切り替えに失敗しました。Scene={scene.path}", this);
                return false;
            }

            entry.Environment?.Apply();
            DynamicGI.UpdateEnvironment();
            return true;
        }
    }
}
