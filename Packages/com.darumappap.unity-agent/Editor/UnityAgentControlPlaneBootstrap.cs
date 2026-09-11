using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// Bootstrap-only path for installing the Control Plane when it does not exist yet.
    /// It installs only the Control Plane; all normal toolchain mutations remain behind it.
    /// </summary>
    internal static class UnityAgentControlPlaneBootstrap
    {
        internal const string Channel = "0.0.7-beta";
        internal const string ReleaseTag = "v0.0.7-beta";

        private static bool s_isRunning;
        internal static bool IsRunning => s_isRunning;

        internal sealed class Result
        {
            internal bool Success;
            internal int ExitCode;
            internal string Output;
            internal string Error;
        }

        internal static bool Start(Action<Result> completed, out string error)
        {
            error = string.Empty;
            if (s_isRunning)
            {
                error = "Control Plane Bootstrapはすでに実行中です。";
                return false;
            }
            if (Application.platform != RuntimePlatform.WindowsEditor)
            {
                error = "現在のControl Plane BootstrapはWindows Editorのみ対応しています。";
                return false;
            }

            var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(typeof(UnityAgentControlPlaneBootstrap).Assembly);
            if (package == null || string.IsNullOrWhiteSpace(package.resolvedPath))
            {
                error = "UnityAgent package pathを解決できませんでした。";
                return false;
            }

            var scriptPath = Path.Combine(package.resolvedPath, "Editor", "Bootstrap~", "install-control-plane.ps1");
            if (!File.Exists(scriptPath))
            {
                error = "Bootstrap scriptが見つかりません: " + scriptPath;
                return false;
            }

            s_isRunning = true;
            Task.Run(() => RunBootstrap(scriptPath)).ContinueWith(task =>
            {
                var result = task.IsFaulted
                    ? new Result
                    {
                        Success = false,
                        ExitCode = -1,
                        Output = string.Empty,
                        Error = task.Exception?.GetBaseException().Message ?? "Unknown bootstrap failure",
                    }
                    : task.Result;

                EditorApplication.delayCall += () =>
                {
                    s_isRunning = false;
                    completed?.Invoke(result);
                };
            });
            return true;
        }

        private static Result RunBootstrap(string scriptPath)
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File " + Quote(scriptPath) +
                            " -ReleaseTag " + Quote(ReleaseTag),
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };

            try
            {
                using (var process = new Process { StartInfo = startInfo })
                {
                    var stdout = new StringBuilder();
                    var stderr = new StringBuilder();
                    process.OutputDataReceived += (_, eventArgs) =>
                    {
                        if (eventArgs.Data != null) stdout.AppendLine(eventArgs.Data);
                    };
                    process.ErrorDataReceived += (_, eventArgs) =>
                    {
                        if (eventArgs.Data != null) stderr.AppendLine(eventArgs.Data);
                    };

                    if (!process.Start())
                    {
                        return Failure(-1, "PowerShell processを起動できませんでした。");
                    }
                    process.BeginOutputReadLine();
                    process.BeginErrorReadLine();
                    if (!process.WaitForExit(180000))
                    {
                        try { process.Kill(); } catch { }
                        return new Result
                        {
                            Success = false,
                            ExitCode = -1,
                            Output = stdout.ToString(),
                            Error = "Control Plane Bootstrapが180秒以内に完了しませんでした。\n" + stderr,
                        };
                    }
                    process.WaitForExit();
                    return new Result
                    {
                        Success = process.ExitCode == 0,
                        ExitCode = process.ExitCode,
                        Output = stdout.ToString(),
                        Error = stderr.ToString(),
                    };
                }
            }
            catch (Exception exception)
            {
                return Failure(-1, exception.GetType().Name + ": " + exception.Message);
            }
        }

        private static Result Failure(int exitCode, string error)
        {
            return new Result
            {
                Success = false,
                ExitCode = exitCode,
                Output = string.Empty,
                Error = error,
            };
        }

        private static string Quote(string value)
        {
            return "\"" + (value ?? string.Empty).Replace("\"", "\\\"") + "\"";
        }
    }
}
