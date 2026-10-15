using System;
using System.IO;
using System.Security.Cryptography;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.SceneManagement;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// 既存Editor Playを観測するUI。動画のEncodeとGame View取得はPlayVideoEncoderが所有する。
    /// Captureファイルの存在はTask E2EやVisual受入のPASSを意味しない。
    /// </summary>
    internal sealed class PlayEvidenceWindow : EditorWindow
    {
        private const double ScreenshotTimeoutSeconds = 20;

        [Serializable]
        private sealed class CaptureEvidence
        {
            public string schema_version = "1.1";
            public string capture_kind = "editor_play";
            public string status;
            public string run_id;
            public string unity_version;
            public string scene_path;
            public string project_path;
            public string started_at_utc;
            public string updated_at_utc;
            public string timeline_director;
            public string timeline_asset_path;
            public string screenshot_path;
            public string screenshot_sha256;
            public string video_path;
            public string video_sha256;
            public string video_stopped_by;
            public string capture_error;
            public string observation = "not_observed";
            public string visual_acceptance = "human_review_required";
            public string e2e_gate = "not_assessed";
            public string video_timing = "realtime_not_frame_exact";
            public int play_frames;
            public int error_count;
            public int video_width;
            public int video_height;
            public int video_fps;
            public int encoded_frames;
            public int skipped_frames;
            public int repeated_frames;
            public double video_elapsed_seconds;
        }

        [SerializeField] private int requestedFps = 30;
        [SerializeField] private int maxDurationSeconds = 90;
        [SerializeField] private float scale = 1f;
        [SerializeField] private PlayableDirector timelineDirector;
        [SerializeField] private string outputDirectory = string.Empty;
        [SerializeField] private string runId = string.Empty;
        [SerializeField] private string startedAt = string.Empty;
        [SerializeField] private string capturedScene = string.Empty;
        [SerializeField] private string status = "NOT_RUN";
        [SerializeField] private string captureError = string.Empty;
        [SerializeField] private string screenshotPath = string.Empty;
        [SerializeField] private string screenshotHash = string.Empty;
        [SerializeField] private string videoPath = string.Empty;
        [SerializeField] private string videoHash = string.Empty;
        [SerializeField] private string stoppedBy = string.Empty;
        [SerializeField] private string recordedDirectorName = string.Empty;
        [SerializeField] private string recordedTimelinePath = string.Empty;
        [SerializeField] private bool screenshotRequested;
        [SerializeField] private bool videoRequested;
        [SerializeField] private bool screenshotPaused;
        [SerializeField] private int errorCount;
        [SerializeField] private int startingFrame;
        [SerializeField] private int observedFrames;
        [SerializeField] private int videoWidth;
        [SerializeField] private int videoHeight;
        [SerializeField] private int videoFps;
        [SerializeField] private int encodedFrames;
        [SerializeField] private int skippedFrames;
        [SerializeField] private int repeatedFrames;
        [SerializeField] private double videoElapsed;
        [SerializeField] private double screenshotDeadline;

        private PlayVideoEncoder recorder;
        private PlayableDirector activeTimeline;
        private double nextPoll;

        [MenuItem("UnityAgent/Play Evidence")]
        internal static void Open()
        {
            var window = GetWindow<PlayEvidenceWindow>("UnityAgent Play Evidence");
            window.minSize = new Vector2(500, 440);
        }

        private void OnEnable()
        {
            EditorApplication.playModeStateChanged += OnPlayModeChanged;
            EditorApplication.update += UpdateCapture;
            Application.logMessageReceived += OnLog;
        }

        private void OnDisable()
        {
            EditorApplication.playModeStateChanged -= OnPlayModeChanged;
            EditorApplication.update -= UpdateCapture;
            Application.logMessageReceived -= OnLog;
            StopRecording("window_closed_or_reload");
            SaveEvidence();
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("Play / Timeline 動作確認", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "BuildせずGame ViewをPNG / H.264 MP4として取得します。" +
                "動画は実時間Captureです。フレーム完全同期や音声録音は保証しません。" +
                "Capture成功はG1/G2・Visual品質の自動PASSではありません。",
                MessageType.Info);

            EditorGUILayout.LabelField("Play", EditorApplication.isPlaying
                ? (EditorApplication.isPaused ? "PAUSED" : "PLAYING") : "STOPPED");

            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUI.DisabledScope(EditorApplication.isPlayingOrWillChangePlaymode))
                {
                    if (GUILayout.Button("Play"))
                    {
                        EditorApplication.isPlaying = true;
                    }
                }
                using (new EditorGUI.DisabledScope(!EditorApplication.isPlaying))
                {
                    if (GUILayout.Button(EditorApplication.isPaused ? "Resume" : "Pause"))
                    {
                        EditorApplication.isPaused = !EditorApplication.isPaused;
                    }
                    if (GUILayout.Button("Stop"))
                    {
                        EditorApplication.isPlaying = false;
                    }
                }
                using (new EditorGUI.DisabledScope(!EditorApplication.isPlaying ||
                    !EditorApplication.isPaused))
                {
                    if (GUILayout.Button("Step"))
                    {
                        EditorApplication.Step();
                    }
                }
            }

            using (new EditorGUI.DisabledScope(recorder != null))
            {
                requestedFps = EditorGUILayout.IntPopup("動画FPS", requestedFps,
                    new[] { "30 FPS", "60 FPS" }, new[] { 30, 60 });
                scale = EditorGUILayout.Popup("録画解像度", Mathf.Approximately(scale, 1f) ? 0 : 1,
                    new[] { "Game View原寸", "50%" }) == 0 ? 1f : 0.5f;
                maxDurationSeconds = EditorGUILayout.IntSlider("最大録画秒数", maxDurationSeconds, 5, 600);
                timelineDirector = (PlayableDirector)EditorGUILayout.ObjectField(
                    "Timeline (任意)", timelineDirector, typeof(PlayableDirector), true);
            }

            using (new EditorGUI.DisabledScope(!EditorApplication.isPlaying || Application.isBatchMode))
            {
                if (GUILayout.Button("Screenshot (PNG)"))
                {
                    CaptureScreenshot();
                }
                if (recorder == null)
                {
                    if (GUILayout.Button("通常Playを録画 (MP4)"))
                    {
                        StartRecording(false);
                    }
                    using (new EditorGUI.DisabledScope(timelineDirector == null ||
                        timelineDirector.playableAsset == null))
                    {
                        if (GUILayout.Button("Timelineを先頭から再生して録画 (MP4)"))
                        {
                            StartRecording(true);
                        }
                    }
                }
                else if (GUILayout.Button("録画を終了して保存"))
                {
                    StopRecording("user_stop");
                }
            }

            EditorGUILayout.Space(5);
            EditorGUILayout.LabelField("Capture", recorder != null ? "RECORDING" : status);
            EditorGUILayout.LabelField("Error / Exception / Assert", errorCount.ToString());
            EditorGUILayout.LabelField("動画フレーム", recorder != null
                ? recorder.EncodedFrames + " / 欠落 " + recorder.SkippedFrames + " / 複製 " + recorder.RepeatedFrames
                : encodedFrames + " / 欠落 " + skippedFrames + " / 複製 " + repeatedFrames);
            if (!string.IsNullOrEmpty(captureError))
            {
                EditorGUILayout.HelpBox(captureError, MessageType.Error);
            }
            if (screenshotPaused)
            {
                EditorGUILayout.HelpBox(
                    "Pause中のスクリーンショットは直前の描画結果を含む場合があります。",
                    MessageType.Warning);
            }
            if (!string.IsNullOrEmpty(outputDirectory))
            {
                EditorGUILayout.SelectableLabel(outputDirectory, GUILayout.Height(35));
                if (GUILayout.Button("Evidenceフォルダを開く") &&
                    Directory.Exists(outputDirectory))
                {
                    EditorUtility.RevealInFinder(outputDirectory);
                }
            }
        }

        private void OnPlayModeChanged(PlayModeStateChange change)
        {
            if (change == PlayModeStateChange.EnteredPlayMode)
            {
                StartNewSession();
            }
            else if (change == PlayModeStateChange.ExitingPlayMode)
            {
                StopRecording("play_mode_exit");
                SaveEvidence();
            }
        }

        private void OnLog(string message, string trace, LogType type)
        {
            if (EditorApplication.isPlaying &&
                (type == LogType.Error || type == LogType.Exception || type == LogType.Assert))
            {
                errorCount++;
            }
        }

        private void StartNewSession()
        {
            // Runの取り違えを防ぐ。Play中にWindowを開いた場合も同じ初期化を行う。
            StopRecording("session_restarted");
            runId = Guid.NewGuid().ToString("N");
            startedAt = DateTime.UtcNow.ToString("o");
            capturedScene = SceneManager.GetActiveScene().path;
            outputDirectory = Path.Combine(Path.GetTempPath(), "UnityAgentPlayEvidence", runId);
            screenshotPath = string.Empty;
            screenshotHash = string.Empty;
            videoPath = string.Empty;
            videoHash = string.Empty;
            recordedDirectorName = string.Empty;
            recordedTimelinePath = string.Empty;
            stoppedBy = string.Empty;
            screenshotRequested = false;
            videoRequested = false;
            screenshotPaused = false;
            screenshotDeadline = 0;
            errorCount = 0;
            observedFrames = 0;
            startingFrame = Time.frameCount;
            videoWidth = videoHeight = videoFps = encodedFrames = skippedFrames = repeatedFrames = 0;
            videoElapsed = 0;
            captureError = string.Empty;
            status = "INCOMPLETE";
            Directory.CreateDirectory(outputDirectory);
            SaveEvidence();
        }

        private void EnsureSession()
        {
            if (!EditorApplication.isPlaying)
            {
                throw new InvalidOperationException("Play Modeで実行してください。");
            }
            if (string.IsNullOrEmpty(outputDirectory))
            {
                StartNewSession();
            }
        }

        private void CaptureScreenshot()
        {
            try
            {
                EnsureSession();
                screenshotPath = Path.Combine(outputDirectory,
                    "game-view-" + Guid.NewGuid().ToString("N") + ".png");
                screenshotHash = string.Empty;
                screenshotRequested = true;
                screenshotPaused = EditorApplication.isPaused;
                screenshotDeadline = EditorApplication.timeSinceStartup + ScreenshotTimeoutSeconds;
                ScreenCapture.CaptureScreenshot(screenshotPath);
                SaveEvidence();
            }
            catch (Exception exception)
            {
                RecordError(exception);
            }
        }

        private void StartRecording(bool timeline)
        {
            try
            {
                EnsureSession();
                if (recorder != null)
                {
                    throw new InvalidOperationException("すでに録画中です。");
                }

                var director = timeline ? timelineDirector : null;
                if (timeline && (director == null || director.playableAsset == null ||
                    !director.isActiveAndEnabled))
                {
                    throw new InvalidOperationException("有効なPlayableDirectorを選択してください。");
                }

                var path = Path.Combine(outputDirectory,
                    "gameplay-" + Guid.NewGuid().ToString("N") + ".mp4");
                recorder = new PlayVideoEncoder(path, requestedFps, scale, maxDurationSeconds);
                videoRequested = true;
                videoPath = path;
                videoHash = string.Empty;
                stoppedBy = string.Empty;
                if (timeline)
                {
                    activeTimeline = director;
                    recordedDirectorName = director.name;
                    recordedTimelinePath = AssetDatabase.GetAssetPath(director.playableAsset);
                    // 既存再生を止めてから購読する。逆順だとStoppedイベントで録画が即終了する。
                    director.Stop();
                    director.time = 0;
                    director.Evaluate();
                    director.stopped += OnTimelineStopped;
                    director.Play();
                }
                status = "RECORDING";
                SaveEvidence();
            }
            catch (Exception exception)
            {
                RecordError(exception);
                StopRecording("start_failed");
            }
        }

        private void OnTimelineStopped(PlayableDirector director)
        {
            if (activeTimeline == director)
            {
                StopRecording("timeline_stopped");
            }
        }

        private void StopRecording(string reason)
        {
            if (activeTimeline != null)
            {
                activeTimeline.stopped -= OnTimelineStopped;
                activeTimeline = null;
            }
            if (recorder == null)
            {
                return;
            }
            var current = recorder;
            recorder = null;
            try
            {
                current.Stop(reason);
                videoWidth = current.Width;
                videoHeight = current.Height;
                videoFps = current.FrameRate;
                encodedFrames = current.EncodedFrames;
                skippedFrames = current.SkippedFrames;
                repeatedFrames = current.RepeatedFrames;
                videoElapsed = current.ElapsedSeconds;
                stoppedBy = current.StopReason;
                if (encodedFrames == 0)
                {
                    captureError = "動画フレームが一枚もエンコードされませんでした。";
                }
                else if (!IsPlausibleMp4(videoPath))
                {
                    captureError = "MP4の実ファイルを確認できません。";
                }
                else
                {
                    videoHash = HashFile(videoPath);
                }
            }
            catch (Exception exception)
            {
                RecordError(exception);
            }
            finally
            {
                current.Dispose();
                SaveEvidence();
            }
        }

        private void UpdateCapture()
        {
            if (string.IsNullOrEmpty(outputDirectory))
            {
                return;
            }

            // 映像取得はEditor Tickごとに行う。Evidence書込だけ間引く。
            if (recorder != null)
            {
                try
                {
                    if (!EditorApplication.isPlaying)
                    {
                        StopRecording("play_mode_exit");
                    }
                    else
                    {
                        recorder.Tick();
                        if (activeTimeline != null && (activeTimeline.state != PlayState.Playing ||
                            (IsFiniteDuration(activeTimeline.duration) &&
                            activeTimeline.time >= activeTimeline.duration)))
                        {
                            StopRecording("timeline_finished");
                        }
                        else if (recorder != null && recorder.DurationReached)
                        {
                            StopRecording("max_duration");
                        }
                    }
                }
                catch (Exception exception)
                {
                    RecordError(exception);
                    StopRecording("capture_failed");
                }
            }

            if (EditorApplication.timeSinceStartup < nextPoll)
            {
                return;
            }
            nextPoll = EditorApplication.timeSinceStartup + 0.25;

            if (screenshotRequested && string.IsNullOrEmpty(screenshotHash) &&
                !string.IsNullOrEmpty(screenshotPath))
            {
                if (IsPlausiblePng(screenshotPath))
                {
                    screenshotHash = HashFile(screenshotPath);
                    screenshotDeadline = 0;
                }
                else if (screenshotDeadline > 0 &&
                    EditorApplication.timeSinceStartup >= screenshotDeadline)
                {
                    captureError = "PNGが保存されませんでした。";
                    screenshotDeadline = 0;
                }
            }

            if (EditorApplication.isPlaying)
            {
                observedFrames = Math.Max(observedFrames, Time.frameCount - startingFrame);
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
                var screenshotOk = screenshotRequested && !string.IsNullOrEmpty(screenshotHash) &&
                    IsPlausiblePng(screenshotPath);
                var videoOk = videoRequested && !string.IsNullOrEmpty(videoHash) &&
                    IsPlausibleMp4(videoPath);
                var complete = (screenshotRequested || videoRequested) &&
                    (!screenshotRequested || screenshotOk) &&
                    (!videoRequested || videoOk);
                status = !string.IsNullOrEmpty(captureError) ? "FAILED" :
                    !complete ? "INCOMPLETE" :
                    errorCount > 0 ? "CAPTURED_WITH_RUNTIME_ERRORS" :
                    skippedFrames > 0 || repeatedFrames > 0 ? "CAPTURED_WITH_TIMING_VARIATION" : "CAPTURED";

                var evidence = new CaptureEvidence
                {
                    run_id = runId,
                    unity_version = Application.unityVersion,
                    scene_path = capturedScene,
                    project_path = Path.GetDirectoryName(Application.dataPath),
                    started_at_utc = startedAt,
                    updated_at_utc = DateTime.UtcNow.ToString("o"),
                    status = status,
                    observation = observedFrames > 0 || encodedFrames > 0
                        ? "observed" : "not_observed",
                    timeline_director = recordedDirectorName,
                    timeline_asset_path = recordedTimelinePath,
                    screenshot_path = screenshotOk ? screenshotPath : null,
                    screenshot_sha256 = screenshotOk ? screenshotHash : null,
                    video_path = videoOk ? videoPath : null,
                    video_sha256 = videoOk ? videoHash : null,
                    video_stopped_by = stoppedBy,
                    capture_error = captureError,
                    play_frames = observedFrames,
                    error_count = errorCount,
                    video_width = videoWidth,
                    video_height = videoHeight,
                    video_fps = videoFps,
                    encoded_frames = encodedFrames,
                    skipped_frames = skippedFrames,
                    repeated_frames = repeatedFrames,
                    video_elapsed_seconds = videoElapsed,
                };
                File.WriteAllText(Path.Combine(outputDirectory, "play-evidence.json"),
                    JsonUtility.ToJson(evidence, true));
            }
            catch (IOException exception)
            {
                status = "FAILED";
                captureError = "Evidence出力失敗: " + exception.Message;
            }
        }

        private void RecordError(Exception exception)
        {
            captureError = exception.GetBaseException().Message;
            status = "FAILED";
            Debug.LogError("[UnityAgent Play Evidence] " + captureError);
        }

        private static bool IsFiniteDuration(double duration)
        {
            return !double.IsNaN(duration) && !double.IsInfinity(duration) && duration > 0;
        }

        private static bool IsPlausiblePng(string path)
        {
            if (string.IsNullOrEmpty(path) || !File.Exists(path) ||
                new FileInfo(path).Length < 100)
            {
                return false;
            }
            using (var file = File.OpenRead(path))
            {
                return file.ReadByte() == 137 && file.ReadByte() == 80 &&
                    file.ReadByte() == 78 && file.ReadByte() == 71;
            }
        }

        private static bool IsPlausibleMp4(string path)
        {
            if (string.IsNullOrEmpty(path) || !File.Exists(path) ||
                new FileInfo(path).Length < 1024)
            {
                return false;
            }
            using (var file = File.OpenRead(path))
            {
                file.Position = 4;
                return file.ReadByte() == 'f' && file.ReadByte() == 't' &&
                    file.ReadByte() == 'y' && file.ReadByte() == 'p';
            }
        }

        private static string HashFile(string path)
        {
            using (var stream = File.OpenRead(path))
            using (var sha = SHA256.Create())
            {
                return BitConverter.ToString(sha.ComputeHash(stream))
                    .Replace("-", "").ToLowerInvariant();
            }
        }
    }
}
