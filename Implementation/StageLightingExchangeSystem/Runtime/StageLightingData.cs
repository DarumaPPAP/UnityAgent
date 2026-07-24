using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

#if UNITY_EDITOR
using UnityEditor;
#endif

namespace StageLighting
{
    /// <summary>
    /// Stage Sceneと対応するEnvironmentおよびベイク済みLighting情報を保持します。
    /// </summary>
    [CreateAssetMenu(fileName = "StageLightingData", menuName = "Stage Lighting/Stage Lighting Data")]
    public sealed class StageLightingData : ScriptableObject
    {
        [SerializeField] private List<StageLightingEntry> _entries = new List<StageLightingEntry>();

        public IReadOnlyList<StageLightingEntry> Entries => _entries;

        /// <summary>
        /// ロードされたSceneに対応する登録情報を取得します。
        /// </summary>
        public bool TryGetEntry(Scene scene, out StageLightingEntry entry)
        {
            entry = null;

            if (!scene.IsValid())
            {
                return false;
            }

            if (!string.IsNullOrEmpty(scene.path))
            {
                for (int i = 0; i < _entries.Count; i++)
                {
                    StageLightingEntry candidate = _entries[i];
                    if (candidate != null && candidate.MatchesPath(scene.path))
                    {
                        entry = candidate;
                        return true;
                    }
                }
            }

            if (string.IsNullOrEmpty(scene.name))
            {
                return false;
            }

            StageLightingEntry nameMatch = null;

            for (int i = 0; i < _entries.Count; i++)
            {
                StageLightingEntry candidate = _entries[i];
                if (candidate == null || !candidate.MatchesName(scene.name))
                {
                    continue;
                }

                // 同名Sceneが複数登録されている場合は誤適用を避けるため一致扱いにしません。
                if (nameMatch != null)
                {
                    return false;
                }

                nameMatch = candidate;
            }

            entry = nameMatch;
            return entry != null;
        }

#if UNITY_EDITOR
        internal bool TryGetEntryByScenePath(string scenePath, out StageLightingEntry entry)
        {
            entry = null;

            if (string.IsNullOrEmpty(scenePath))
            {
                return false;
            }

            for (int i = 0; i < _entries.Count; i++)
            {
                StageLightingEntry candidate = _entries[i];
                if (candidate != null && candidate.MatchesPath(scenePath))
                {
                    entry = candidate;
                    return true;
                }
            }

            return false;
        }

        internal bool RefreshSceneIdentities()
        {
            bool changed = false;

            for (int i = 0; i < _entries.Count; i++)
            {
                StageLightingEntry entry = _entries[i];
                if (entry != null)
                {
                    changed |= entry.RefreshSceneIdentity();
                }
            }

            return changed;
        }

        private void OnValidate()
        {
            RefreshSceneIdentities();
        }
#endif
    }

    /// <summary>
    /// 1つのStage Sceneに対応するLighting情報を保持します。
    /// </summary>
    [Serializable]
    public sealed class StageLightingEntry
    {
#if UNITY_EDITOR
        [Header("Scene")]
        [SerializeField] private SceneAsset _sceneAsset;

        [Header("Lighting")]
        [SerializeField] private LightingSettings _lightingSettings;
        [SerializeField] private LightingDataAsset _lightingDataAsset;
#endif

        [SerializeField, HideInInspector] private string _sceneGuid;
        [SerializeField, HideInInspector] private string _scenePath;
        [SerializeField, HideInInspector] private string _sceneName;

        [Header("Environment")]
        [SerializeField] private StageEnvironmentSettings _environment = new StageEnvironmentSettings();

        public string ScenePath => _scenePath;

        public string SceneName => _sceneName;

        public StageEnvironmentSettings Environment => _environment;

        internal bool MatchesPath(string scenePath)
        {
            return string.Equals(_scenePath, scenePath, StringComparison.Ordinal);
        }

        internal bool MatchesName(string sceneName)
        {
            return string.Equals(_sceneName, sceneName, StringComparison.Ordinal);
        }

#if UNITY_EDITOR
        internal SceneAsset SceneAsset => _sceneAsset;

        internal LightingSettings LightingSettings => _lightingSettings;

        internal LightingDataAsset LightingDataAsset => _lightingDataAsset;

        internal bool RefreshSceneIdentity()
        {
            string scenePath = _sceneAsset != null
                ? AssetDatabase.GetAssetPath(_sceneAsset)
                : string.Empty;

            string sceneGuid = string.IsNullOrEmpty(scenePath)
                ? string.Empty
                : AssetDatabase.AssetPathToGUID(scenePath);

            string sceneName = string.IsNullOrEmpty(scenePath)
                ? string.Empty
                : Path.GetFileNameWithoutExtension(scenePath);

            bool changed = false;
            changed |= AssignIfChanged(ref _scenePath, scenePath);
            changed |= AssignIfChanged(ref _sceneGuid, sceneGuid);
            changed |= AssignIfChanged(ref _sceneName, sceneName);
            return changed;
        }

        internal bool CaptureEditorState(Scene scene)
        {
            bool changed = RefreshSceneIdentity();

            LightingSettings lightingSettings = Lightmapping.GetLightingSettingsForScene(scene);
            LightingDataAsset lightingDataAsset = Lightmapping.GetLightingDataAssetForScene(scene);

            if (_lightingSettings != lightingSettings)
            {
                _lightingSettings = lightingSettings;
                changed = true;
            }

            if (_lightingDataAsset != lightingDataAsset)
            {
                _lightingDataAsset = lightingDataAsset;
                changed = true;
            }

            if (_environment == null)
            {
                _environment = new StageEnvironmentSettings();
                changed = true;
            }

            changed |= _environment.CaptureFromRenderSettings();
            return changed;
        }

        internal void ApplyEditorState(Scene scene)
        {
            Lightmapping.SetLightingSettingsForScene(scene, _lightingSettings);
            Lightmapping.SetLightingDataAssetForScene(scene, _lightingDataAsset);
            _environment?.Apply();
        }

        private static bool AssignIfChanged(ref string target, string value)
        {
            if (string.Equals(target, value, StringComparison.Ordinal))
            {
                return false;
            }

            target = value;
            return true;
        }
#endif
    }

    /// <summary>
    /// LightingウィンドウのEnvironment相当の値を保持します。
    /// </summary>
    [Serializable]
    public sealed class StageEnvironmentSettings
    {
        [Header("Skybox")]
        [SerializeField] private Material _skyboxMaterial;

        [Header("Ambient")]
        [SerializeField] private AmbientMode _ambientMode = AmbientMode.Skybox;
        [SerializeField] private Color _ambientSkyColor = Color.gray;
        [SerializeField] private Color _ambientEquatorColor = Color.gray;
        [SerializeField] private Color _ambientGroundColor = Color.gray;
        [SerializeField] private Color _ambientLight = Color.gray;
        [SerializeField, Min(0.0f)] private float _ambientIntensity = 1.0f;

        [Header("Reflection")]
        [SerializeField] private DefaultReflectionMode _defaultReflectionMode = DefaultReflectionMode.Skybox;
        [SerializeField] private Texture _customReflection;
        [SerializeField, Min(16)] private int _defaultReflectionResolution = 128;
        [SerializeField, Min(0.0f)] private float _reflectionIntensity = 1.0f;
        [SerializeField, Min(1)] private int _reflectionBounces = 1;

        [Header("Fog")]
        [SerializeField] private bool _fogEnabled;
        [SerializeField] private FogMode _fogMode = FogMode.ExponentialSquared;
        [SerializeField] private Color _fogColor = Color.gray;
        [SerializeField, Min(0.0f)] private float _fogDensity = 0.01f;
        [SerializeField] private float _fogStartDistance;
        [SerializeField] private float _fogEndDistance = 300.0f;

        [Header("Other")]
        [SerializeField] private Color _subtractiveShadowColor = Color.black;
        [SerializeField, Min(0.0f)] private float _haloStrength = 0.5f;
        [SerializeField, Min(0.0f)] private float _flareStrength = 1.0f;
        [SerializeField, Min(0.0f)] private float _flareFadeSpeed = 3.0f;

        internal void Apply()
        {
            RenderSettings.skybox = _skyboxMaterial;

            RenderSettings.ambientMode = _ambientMode;
            RenderSettings.ambientSkyColor = _ambientSkyColor;
            RenderSettings.ambientEquatorColor = _ambientEquatorColor;
            RenderSettings.ambientGroundColor = _ambientGroundColor;
            RenderSettings.ambientLight = _ambientLight;
            RenderSettings.ambientIntensity = _ambientIntensity;

            RenderSettings.defaultReflectionMode = _defaultReflectionMode;
            RenderSettings.customReflection = _customReflection;
            RenderSettings.defaultReflectionResolution = _defaultReflectionResolution;
            RenderSettings.reflectionIntensity = _reflectionIntensity;
            RenderSettings.reflectionBounces = _reflectionBounces;

            RenderSettings.fog = _fogEnabled;
            RenderSettings.fogMode = _fogMode;
            RenderSettings.fogColor = _fogColor;
            RenderSettings.fogDensity = _fogDensity;
            RenderSettings.fogStartDistance = _fogStartDistance;
            RenderSettings.fogEndDistance = _fogEndDistance;

            RenderSettings.subtractiveShadowColor = _subtractiveShadowColor;
            RenderSettings.haloStrength = _haloStrength;
            RenderSettings.flareStrength = _flareStrength;
            RenderSettings.flareFadeSpeed = _flareFadeSpeed;
        }

#if UNITY_EDITOR
        internal bool CaptureFromRenderSettings()
        {
            bool changed = false;

            changed |= AssignIfChanged(ref _skyboxMaterial, RenderSettings.skybox);

            changed |= AssignIfChanged(ref _ambientMode, RenderSettings.ambientMode);
            changed |= AssignIfChanged(ref _ambientSkyColor, RenderSettings.ambientSkyColor);
            changed |= AssignIfChanged(ref _ambientEquatorColor, RenderSettings.ambientEquatorColor);
            changed |= AssignIfChanged(ref _ambientGroundColor, RenderSettings.ambientGroundColor);
            changed |= AssignIfChanged(ref _ambientLight, RenderSettings.ambientLight);
            changed |= AssignIfChanged(ref _ambientIntensity, RenderSettings.ambientIntensity);

            changed |= AssignIfChanged(ref _defaultReflectionMode, RenderSettings.defaultReflectionMode);
            changed |= AssignIfChanged(ref _customReflection, RenderSettings.customReflection);
            changed |= AssignIfChanged(ref _defaultReflectionResolution, RenderSettings.defaultReflectionResolution);
            changed |= AssignIfChanged(ref _reflectionIntensity, RenderSettings.reflectionIntensity);
            changed |= AssignIfChanged(ref _reflectionBounces, RenderSettings.reflectionBounces);

            changed |= AssignIfChanged(ref _fogEnabled, RenderSettings.fog);
            changed |= AssignIfChanged(ref _fogMode, RenderSettings.fogMode);
            changed |= AssignIfChanged(ref _fogColor, RenderSettings.fogColor);
            changed |= AssignIfChanged(ref _fogDensity, RenderSettings.fogDensity);
            changed |= AssignIfChanged(ref _fogStartDistance, RenderSettings.fogStartDistance);
            changed |= AssignIfChanged(ref _fogEndDistance, RenderSettings.fogEndDistance);

            changed |= AssignIfChanged(ref _subtractiveShadowColor, RenderSettings.subtractiveShadowColor);
            changed |= AssignIfChanged(ref _haloStrength, RenderSettings.haloStrength);
            changed |= AssignIfChanged(ref _flareStrength, RenderSettings.flareStrength);
            changed |= AssignIfChanged(ref _flareFadeSpeed, RenderSettings.flareFadeSpeed);

            return changed;
        }

        private static bool AssignIfChanged<T>(ref T target, T value)
        {
            if (EqualityComparer<T>.Default.Equals(target, value))
            {
                return false;
            }

            target = value;
            return true;
        }

        private static bool AssignIfChanged(ref float target, float value)
        {
            if (Mathf.Approximately(target, value))
            {
                return false;
            }

            target = value;
            return true;
        }
#endif
    }
}
