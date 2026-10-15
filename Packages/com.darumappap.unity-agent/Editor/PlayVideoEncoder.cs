using System;
using System.Reflection;
using UnityEditor;
using UnityEditor.Media;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// 対話型EditorのGame View合成結果をMediaEncoderで記録する。
    /// Unity非公開のPlayModeView参照はこのクラス内に隔離し、利用不可なら明示的に失敗する。
    /// </summary>
    internal sealed class PlayVideoEncoder : IDisposable
    {
        private readonly MediaEncoder encoder;
        private readonly Texture2D frameTexture;
        private readonly RenderTexture readbackTarget;
        private readonly int frameRate;

        // Editor内部API解決はDomain Reloadごとに一度だけ行う。
        private static readonly Type s_viewType =
            typeof(Editor).Assembly.GetType("UnityEditor.PlayModeView");
        private static readonly MethodInfo s_getMainView = s_viewType?.GetMethod(
            "GetMainPlayModeView", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
        private static readonly FieldInfo s_targetTexture = s_viewType?.GetField(
            "m_TargetTexture", BindingFlags.Instance | BindingFlags.NonPublic);
        private readonly double startedAt;
        private readonly double maxDuration;
        private readonly int sourceWidth;
        private readonly int sourceHeight;
        private readonly float scale;
        private bool disposed;
        private int encodedFrames;
        private int skippedFrames;
        private int repeatedFrames;
        private double elapsedAtStop;
        private string stopReason;

        internal string OutputPath { get; }
        internal int Width { get; }
        internal int Height { get; }
        internal int FrameRate => frameRate;
        internal int EncodedFrames => encodedFrames;
        internal int SkippedFrames => skippedFrames;
        internal int RepeatedFrames => repeatedFrames;
        internal bool IsRecording => !disposed;
        internal string StopReason => stopReason;
        internal double ElapsedSeconds => disposed ? elapsedAtStop :
            Math.Max(0, EditorApplication.timeSinceStartup - startedAt);
        internal bool DurationReached => ElapsedSeconds >= maxDuration;

        internal PlayVideoEncoder(string outputPath, int fps, float resolutionScale, double limitSeconds)
        {
            if (!Application.isPlaying || Application.isBatchMode)
            {
                throw new InvalidOperationException("映像録画には描画可能なEditor Play Modeが必要です。");
            }
            if (Application.platform != RuntimePlatform.WindowsEditor &&
                Application.platform != RuntimePlatform.OSXEditor)
            {
                throw new PlatformNotSupportedException("H.264 MP4はWindows/macOS Editorのみ対応です。");
            }
            if (fps != 30 && fps != 60)
            {
                throw new ArgumentOutOfRangeException(nameof(fps), "FPSは30または60です。");
            }
            if (resolutionScale != 1f && resolutionScale != 0.5f)
            {
                throw new ArgumentOutOfRangeException(nameof(resolutionScale));
            }
            if (limitSeconds < 1 || limitSeconds > 600)
            {
                throw new ArgumentOutOfRangeException(nameof(limitSeconds));
            }

            var renderTarget = GetGameViewRenderTexture();
            if (renderTarget == null || !renderTarget.IsCreated())
            {
                throw new InvalidOperationException(
                    "Game Viewの描画結果を取得できません。Game Viewを表示してCameraを描画してください。");
            }

            sourceWidth = renderTarget.width;
            sourceHeight = renderTarget.height;
            scale = resolutionScale;
            Width = Mathf.FloorToInt(sourceWidth * scale) & ~1;
            Height = Mathf.FloorToInt(sourceHeight * scale) & ~1;
            if (Width < 2 || Height < 2)
            {
                throw new InvalidOperationException("録画解像度が不正です。");
            }

            var h264 = new H264EncoderAttributes
            {
                gopSize = fps,
                numConsecutiveBFrames = 2,
                profile = VideoEncodingProfile.H264High,
            };
            var video = new VideoTrackEncoderAttributes(h264)
            {
                frameRate = new MediaRational(fps),
                width = (uint)Width,
                height = (uint)Height,
                targetBitRate = Width * Height >= 3840 * 2160 ? 40000000u : 16000000u,
                includeAlpha = false,
            };

            // エンコーダの破棄時にコンテナが確定する。開始失敗時も資源を保持しない。
            MediaEncoder createdEncoder = null;
            Texture2D createdTexture = null;
            RenderTexture createdTarget = null;
            try
            {
                createdEncoder = new MediaEncoder(outputPath, video);
                createdTexture = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
                createdTexture.hideFlags = HideFlags.HideAndDontSave;
                createdTarget = new RenderTexture(Width, Height, 0, RenderTextureFormat.ARGB32,
                    RenderTextureReadWrite.sRGB);
                createdTarget.hideFlags = HideFlags.HideAndDontSave;
                if (!createdTarget.Create())
                {
                    throw new InvalidOperationException("Readback RenderTextureの生成に失敗しました。");
                }
                encoder = createdEncoder;
                frameTexture = createdTexture;
                readbackTarget = createdTarget;
            }
            catch
            {
                createdEncoder?.Dispose();
                if (createdTexture != null)
                {
                    UnityEngine.Object.DestroyImmediate(createdTexture);
                }
                if (createdTarget != null)
                {
                    createdTarget.Release();
                    UnityEngine.Object.DestroyImmediate(createdTarget);
                }
                throw;
            }

            OutputPath = outputPath;
            frameRate = fps;
            maxDuration = limitSeconds;
            startedAt = EditorApplication.timeSinceStartup;
        }

        /// <summary>
        /// 実時間に基づき最大1つの描画結果を取得し、停止時間は重複フレームで補正する。
        /// 取得不能なフレーム数はSkippedFramesに残し、正常録画として扱わない。
        /// </summary>
        internal void Tick()
        {
            if (disposed)
            {
                return;
            }

            var expected = (int)Math.Floor(ElapsedSeconds * frameRate);
            var due = expected - encodedFrames - skippedFrames;
            if (due <= 0)
            {
                return;
            }

            // 長時間Editor停止後のバーストを制限する。
            var boundedDue = Math.Min(due, frameRate);
            if (due > boundedDue)
            {
                skippedFrames += due - boundedDue;
            }

            var renderTarget = GetGameViewRenderTexture();
            if (renderTarget == null || !renderTarget.IsCreated() ||
                renderTarget.width != sourceWidth || renderTarget.height != sourceHeight)
            {
                skippedFrames += boundedDue;
                return;
            }

            if (!TryCopyFrame(renderTarget))
            {
                skippedFrames += boundedDue;
                return;
            }

            for (var index = 0; index < boundedDue; index++)
            {
                if (encoder.AddFrame(frameTexture))
                {
                    encodedFrames++;
                    if (index > 0)
                    {
                        // 同じ描画結果を繰り返して固定FPSの動画時間を維持したことを明示する。
                        repeatedFrames++;
                    }
                }
                else
                {
                    skippedFrames++;
                }
            }
        }

        private bool TryCopyFrame(RenderTexture renderTarget)
        {
            var previous = RenderTexture.active;
            try
            {
                // Game View RTはそのままReadPixelsすると上下反転するため描画方向を補正する。
                Graphics.Blit(renderTarget, readbackTarget, new Vector2(1f, -1f), new Vector2(0f, 1f));
                RenderTexture.active = readbackTarget;
                frameTexture.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                frameTexture.Apply(false, false);
                return true;
            }
            finally
            {
                RenderTexture.active = previous;
            }
        }

        internal void Stop(string reason)
        {
            if (disposed)
            {
                return;
            }
            stopReason = reason;
            Dispose();
        }

        public void Dispose()
        {
            if (disposed)
            {
                return;
            }
            disposed = true;
            elapsedAtStop = Math.Max(0, EditorApplication.timeSinceStartup - startedAt);
            try
            {
                encoder.Dispose();
            }
            finally
            {
                if (frameTexture != null)
                {
                    UnityEngine.Object.DestroyImmediate(frameTexture);
                }
                if (readbackTarget != null)
                {
                    readbackTarget.Release();
                    UnityEngine.Object.DestroyImmediate(readbackTarget);
                }
            }
        }

        // Game View/Device Simulatorの最終合成RT。Unity 6内部APIのためアクセス失敗時はFail Closed。
        private static RenderTexture GetGameViewRenderTexture()
        {
            if (s_getMainView == null || s_targetTexture == null)
            {
                return null;
            }

            try
            {
                var window = s_getMainView.Invoke(null, null) as EditorWindow;
                return window == null ? null : s_targetTexture.GetValue(window) as RenderTexture;
            }
            catch (TargetInvocationException)
            {
                return null;
            }
        }
    }
}
