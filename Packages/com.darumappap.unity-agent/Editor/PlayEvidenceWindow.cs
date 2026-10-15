using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// 現在のEditor Playを観測するためのローカル診断入口。
    /// 取得した映像は実機・Player・E2E成功を証明しない。
    /// </summary>
    internal sealed class PlayEvidenceWindow : EditorWindow
    {
        private const int RecordingFrameRate = 15;
        private const double CaptureTimeoutSeconds = 20.0;

        [Serializable]
        private sealed class CaptureEvidence
        {
            public string schema_version = "1.0";
            public string capture_kind = "editor_play";
            public string observation = "not_observed";
            public string status = "NOT_RUN";
            public string run_id;
            public string unity_version;
            public string scene_path;
            public string project_path;
            public string started_at_utc;
            public string updated_at_utc;
            public string screenshot_path;
            public string screenshot_sha256;
            public string video_path;
            public string video_sha256;
            public int play_frames;
            public int error_count;
            public string capture_error;
            public string visual_acceptance = "human_review_required";
            public string e2e_gate = "not_assessed";
        }

        [SerializeField] private string outputDirectory = string.Empty;
        [SerializeField] private string runId = string.Empty;
        [SerializeField] private string startedAtUtc = string.Empty;
        [SerializeField] private string capturedScene = string.Empty;
        [SerializeField] private string status = "NOT_RUN";
        [SerializeField] private string captureError = string.Empty;
        [SerializeField] private bool screenshotRequested;
        [SerializeField] private bool videoRequested;
        [SerializeField] private int errorCount;
        [SerializeField] private int startingFrame;
        [SerializeField] private int observedFrames;
        [SerializeField] private string screenshotPath = string.Empty;
        [SerializeField] private string videoPath = string.Empty;
        [SerializeField] private string screenshotSha256 = string.Empty;
        [SerializeField] private string videoSha256 = string.Empty;

        private object recorderController;
        private UnityEngine.Object controllerSettings;
        private UnityEngine.Object movieSettings;
        private bool recording;
        private double screenshotDeadline;
        private double videoDeadline;
        private double nextEvidenceRefresh;
        private long lastVideoFileSize;
        private double lastVideoSizeChange;

        [MenuItem("UnityAgent/Play Evidence")]
        internal static void Open()
        {
            GetWindow<PlayEvidenceWindow>("UnityAgent Play Evidence").minSize = new Vector2(460f, 310f);
        }

        private void OnEnable()
        {
            EditorApplication.playModeStateChanged += OnPlayModeChanged;
            EditorApplication.update += UpdateEvidence;
            Application.logMessageReceived += OnLogMessage;
        }

        private void OnDisable()
        {
            EditorApplication.playModeStateChanged -= OnPlayModeChanged;
            EditorApplication.update -= UpdateEvidence;
            Application.logMessageReceived -= OnLogMessage;
            StopRecording();
            SaveEvidence();
            ReleaseRecorderSettings();
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("Play Mode 動作確認", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "Player Buildは行いません。Game ViewのPNGと録画を外部一時フォルダへ保存します。" +
                "映像があってもG1/G2・Visual受入は自動PASSにはなりません。",
                MessageType.Info);

            EditorGUILayout.LabelField("Play状態", EditorApplication.isPlaying ? "PLAYING" : "STOPPED");
            EditorGUILayout.LabelField("Capture状態", recording ? "RECORDING" : status);
            EditorGUILayout.LabelField("Console Error/Exception/Assert", errorCount.ToString());
            if (!string.IsNullOrEmpty(captureError))
            {
                EditorGUILayout.HelpBox(captureError, MessageType.Warning);
            }

            using (new EditorGUI.DisabledScope(EditorApplication.isPlayingOrWillChangePlaymode))
            {
                if (GUILayout.Button("Playを開始", GUILayout.Height(28)))
                {
                    EditorApplication.isPlaying = true;
                }
            }

            using (new EditorGUI.DisabledScope(!EditorApplication.isPlaying))
            {
                if (GUILayout.Button("スクリーンショット取得（PNG）", GUILayout.Height(28)))
                {
                    CaptureScreenshot();
                }

                var recorderAvailable = FindRecorderType("UnityEditor.Recorder.RecorderController") != null;
                using (new EditorGUI.DisabledScope(!recorderAvailable))
                {
                    if (GUILayout.Button(recording ? "録画を終了" : "録画を開始（MP4 / 15fps）",
                            GUILayout.Height(28)))
                    {
                        if (recording)
                        {
                            StopRecording();
                        }
                        else
                        {
                            StartRecording();
                        }
                    }
                }
                if (!recorderAvailable)
                {
                    EditorGUILayout.HelpBox(
                        "録画には公式 com.unity.recorder 5.1系が必要です。" +
                        "Package Managerで明示的に導入してください（自動Installしません）。",
                        MessageType.Warning);
                }
            }

            using (new EditorGUI.DisabledScope(!EditorApplication.isPlaying))
            {
                if (GUILayout.Button("Playを終了"))
                {
                    EditorApplication.isPlaying = false;
                }
            }

            if (!string.IsNullOrEmpty(outputDirectory))
            {
                EditorGUILayout.SelectableLabel(outputDirectory, GUILayout.Height(34));
                if (GUILayout.Button("Evidenceフォルダを開く") && Directory.Exists(outputDirectory))
                {
                    EditorUtility.RevealInFinder(outputDirectory);
                }
            }
        }

        private void OnPlayModeChanged(PlayModeStateChange change)
        {
            if (change == PlayModeStateChange.EnteredPlayMode)
            {
                // 新しいPlayごとにRun IDとCaptureファイルを分離する。
                outputDirectory = string.Empty;
                screenshotRequested = false;
                videoRequested = false;
                screenshotPath = string.Empty;
                videoPath = string.Empty;
                screenshotSha256 = string.Empty;
                videoSha256 = string.Empty;
                screenshotDeadline = 0;
                videoDeadline = 0;
                lastVideoFileSize = 0;
                lastVideoSizeChange = 0;
                BeginSession();
            }
            else if (change == PlayModeStateChange.ExitingPlayMode)
            {
                StopRecording();
                SaveEvidence();
            }
            else if (change == PlayModeStateChange.EnteredEditMode)
            {
                SaveEvidence();
            }
        }

        private void OnLogMessage(string message, string stackTrace, LogType type)
        {
            if (EditorApplication.isPlaying &&
                (type == LogType.Error || type == LogType.Exception || type == LogType.Assert))
            {
                errorCount++;
            }
        }

        private void BeginSession()
        {
            if (!EditorApplication.isPlaying)
            {
                throw new InvalidOperationException("Play Mode中のみCaptureできます。");
            }

            if (!string.IsNullOrEmpty(outputDirectory))
            {
                return;
            }

            runId = Guid.NewGuid().ToString("N");
            startedAtUtc = DateTime.UtcNow.ToString("o");
            capturedScene = SceneManager.GetActiveScene().path;
            outputDirectory = Path.Combine(Path.GetTempPath(), "UnityAgentPlayEvidence", runId);
            Directory.CreateDirectory(outputDirectory);
            startingFrame = Time.frameCount;
            observedFrames = 0;
            errorCount = 0;
            status = "RUNNING";
            captureError = string.Empty;
        }

        private void CaptureScreenshot()
        {
            try
            {
                BeginSession();
                screenshotPath = Path.Combine(outputDirectory, "game-view-" + Guid.NewGuid().ToString("N") + ".png");
                screenshotSha256 = string.Empty;
                // CaptureScreenshotは非同期保存される場合があるので、ファイルを観測してから記録する。
                ScreenCapture.CaptureScreenshot(screenshotPath);
                screenshotRequested = true;
                screenshotDeadline = EditorApplication.timeSinceStartup + CaptureTimeoutSeconds;
                status = "CAPTURING";
                SaveEvidence();
            }
            catch (Exception exception)
            {
                captureError = exception.Message;
                status = "FAILED";
                SaveEvidence();
            }
        }

        private void StartRecording()
        {
            try
            {
                BeginSession();
                if (recording)
                {
                    return;
                }

                var controllerType = RequireRecorderType("UnityEditor.Recorder.RecorderController");
                var settingsType = RequireRecorderType("UnityEditor.Recorder.RecorderControllerSettings");
                var movieType = RequireRecorderType("UnityEditor.Recorder.MovieRecorderSettings");
                var inputType = RequireRecorderType("UnityEditor.Recorder.Input.GameViewInputSettings");

                controllerSettings = ScriptableObject.CreateInstance(settingsType);
                movieSettings = ScriptableObject.CreateInstance(movieType);
                SetProperty(controllerSettings, "FrameRate", (float)RecordingFrameRate);
                SetProperty(controllerSettings, "CapFrameRate", false);
                SetProperty(controllerSettings, "ExitPlayMode", false);
                InvokeMethod(controllerSettings, "SetRecordModeToManual");

                // Recorder 5.1のGame View入力とH.264 MP4を利用する。
                SetProperty(movieSettings, "ImageInputSettings", Activator.CreateInstance(inputType));
                SetProperty(movieSettings, "CaptureAudio", false);
                var outputFormat = movieType.GetProperty("OutputFormat");
                if (outputFormat == null || !outputFormat.CanWrite)
                {
                    throw new MissingMemberException("Recorder MP4 OutputFormat is unavailable");
                }
                outputFormat.SetValue(movieSettings, Enum.Parse(outputFormat.PropertyType, "MP4"), null);
                SetProperty(movieSettings, "OutputFile", Path.Combine(outputDirectory, "gameplay"));
                InvokeMethod(controllerSettings, "AddRecorderSettings", movieSettings);
                recorderController = Activator.CreateInstance(controllerType, controllerSettings);
                InvokeMethod(recorderController, "PrepareRecording");
                if (!(bool)InvokeMethod(recorderController, "StartRecording"))
                {
                    throw new InvalidOperationException("Unity Recorderは録画を開始できませんでした。Consoleを確認してください。");
                }

                recording = true;
                videoRequested = true;
                status = "RECORDING";
                SaveEvidence();
            }
            catch (Exception exception)
            {
                captureError = exception.GetBaseException().Message;
                status = "FAILED";
                StopRecording();
                ReleaseRecorderSettings();
                SaveEvidence();
            }
        }

        private void StopRecording()
        {
            if (recorderController == null)
            {
                return;
            }

            try
            {
                InvokeMethod(recorderController, "StopRecording");
                videoDeadline = EditorApplication.timeSinceStartup + CaptureTimeoutSeconds;
                status = "FINALIZING_VIDEO";
            }
            catch (Exception exception)
            {
                captureError = exception.GetBaseException().Message;
                status = "FAILED";
            }
            finally
            {
                recorderController = null;
                recording = false;
                SaveEvidence();
            }
        }

        private void UpdateEvidence()
        {
            if (string.IsNullOrEmpty(outputDirectory) || !Directory.Exists(outputDirectory) ||
                EditorApplication.timeSinceStartup < nextEvidenceRefresh)
            {
                return;
            }

            nextEvidenceRefresh = EditorApplication.timeSinceStartup + 0.5;
            if (screenshotRequested)
            {
                var candidate = screenshotPath;
                if (File.Exists(candidate) && new FileInfo(candidate).Length > 100)
                {
                    if (string.IsNullOrEmpty(screenshotSha256))
                    {
                        screenshotSha256 = CalculateSha256(candidate);
                    }
                    screenshotDeadline = 0;
                }
                else if (EditorApplication.timeSinceStartup > screenshotDeadline && screenshotDeadline > 0)
                {
                    captureError = "スクリーンショットを取得できませんでした。";
                    screenshotDeadline = 0;
                }
            }

            if (videoRequested && !recording && videoDeadline > 0)
            {
                var candidate = Path.Combine(outputDirectory, "gameplay.mp4");
                if (File.Exists(candidate) && new FileInfo(candidate).Length > 1024)
                {
                    var size = new FileInfo(candidate).Length;
                    if (size != lastVideoFileSize)
                    {
                        lastVideoFileSize = size;
                        lastVideoSizeChange = EditorApplication.timeSinceStartup;
                    }
                    else if (EditorApplication.timeSinceStartup - lastVideoSizeChange >= 1.0)
                    {
                        videoPath = candidate;
                        videoSha256 = CalculateSha256(candidate);
                        videoDeadline = 0;
                        ReleaseRecorderSettings();
                    }
                }
                else if (EditorApplication.timeSinceStartup > videoDeadline)
                {
                    captureError = "MP4の生成を確認できませんでした。Recorderのログを確認してください。";
                    videoDeadline = 0;
                    ReleaseRecorderSettings();
                }
            }

            SaveEvidence();
            Repaint();
        }

        private void SaveEvidence()
        {
            if (string.IsNullOrEmpty(outputDirectory) || !Directory.Exists(outputDirectory))
            {
                return;
            }

            try
            {
                var screenshotValid = screenshotRequested && !string.IsNullOrEmpty(screenshotSha256) &&
                    File.Exists(screenshotPath);
                var videoValid = videoRequested && !string.IsNullOrEmpty(videoSha256) &&
                    File.Exists(videoPath);
                var requestedComplete = (screenshotRequested || videoRequested) &&
                    (!screenshotRequested || screenshotValid) && (!videoRequested || videoValid);
                if (EditorApplication.isPlaying)
                {
                    observedFrames = Math.Max(observedFrames, Math.Max(0, Time.frameCount - startingFrame));
                }
                var measuredFrames = observedFrames;
                var captureStatus = requestedComplete && measuredFrames > 0 && string.IsNullOrEmpty(captureError)
                    ? (errorCount == 0 ? "CAPTURED" : "CAPTURED_WITH_RUNTIME_ERRORS")
                    : status == "FAILED" || !string.IsNullOrEmpty(captureError) ? "FAILED" : "INCOMPLETE";
                var evidence = new CaptureEvidence
                {
                    run_id = runId,
                    unity_version = Application.unityVersion,
                    scene_path = capturedScene,
                    project_path = Path.GetDirectoryName(Application.dataPath),
                    started_at_utc = startedAtUtc,
                    updated_at_utc = DateTime.UtcNow.ToString("o"),
                    observation = measuredFrames > 0 ? "observed" : "not_observed",
                    status = captureStatus,
                    screenshot_path = screenshotValid ? screenshotPath : null,
                    screenshot_sha256 = screenshotValid ? screenshotSha256 : null,
                    video_path = videoValid ? videoPath : null,
                    video_sha256 = videoValid ? videoSha256 : null,
                    play_frames = measuredFrames,
                    error_count = errorCount,
                    capture_error = captureError,
                };
                File.WriteAllText(Path.Combine(outputDirectory, "play-evidence.json"),
                    JsonUtility.ToJson(evidence, true));
                status = captureStatus;
            }
            catch (Exception exception)
            {
                status = "FAILED";
                captureError = "Evidence保存失敗: " + exception.Message;
            }
        }

        private void ReleaseRecorderSettings()
        {
            if (controllerSettings != null)
            {
                DestroyImmediate(controllerSettings);
                controllerSettings = null;
            }
            if (movieSettings != null)
            {
                DestroyImmediate(movieSettings);
                movieSettings = null;
            }
        }

        private static string CalculateSha256(string filename)
        {
            using (var stream = File.OpenRead(filename))
            using (var algorithm = SHA256.Create())
            {
                return BitConverter.ToString(algorithm.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            }
        }

        private static Type FindRecorderType(string name)
        {
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                var type = assembly.GetType(name, false);
                if (type != null)
                {
                    return type;
                }
            }
            return null;
        }

        private static Type RequireRecorderType(string name)
        {
            return FindRecorderType(name) ?? throw new InvalidOperationException(
                "Unity Recorder APIが見つかりません: " + name);
        }

        private static void SetProperty(object target, string name, object value)
        {
            var property = target.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
            if (property == null || !property.CanWrite)
            {
                throw new MissingMemberException(target.GetType().FullName, name);
            }
            property.SetValue(target, value, null);
        }

        private static object InvokeMethod(object target, string name, params object[] arguments)
        {
            var method = target.GetType().GetMethod(name, BindingFlags.Public | BindingFlags.Instance);
            if (method == null)
            {
                throw new MissingMethodException(target.GetType().FullName, name);
            }
            return method.Invoke(target, arguments);
        }
    }
}
