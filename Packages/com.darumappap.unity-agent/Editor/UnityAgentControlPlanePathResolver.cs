using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using UnityEditor;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// Resolves the UnityAgent Control Plane executable without relying only on the PATH
    /// inherited by Unity Hub. Resolution is filesystem-only; execution remains owned by
    /// UnityAgentControlPlaneClient.
    /// </summary>
    internal static class UnityAgentControlPlanePathResolver
    {
        internal const string EditorPrefKey = "DarumaPPAP.UnityAgent.ControlPlanePath";
        internal const string EnvironmentVariable = "UNITY_AGENT_CONTROL_PLANE";

        internal static bool HasOverride => !string.IsNullOrWhiteSpace(EditorPrefs.GetString(EditorPrefKey, string.Empty));

        internal static string GetOverride()
        {
            return EditorPrefs.GetString(EditorPrefKey, string.Empty);
        }

        internal static bool TrySetOverride(string path, out string error)
        {
            error = string.Empty;
            if (string.IsNullOrWhiteSpace(path))
            {
                ClearOverride();
                return true;
            }

            string fullPath;
            try
            {
                fullPath = Path.GetFullPath(path.Trim());
            }
            catch (Exception exception)
            {
                error = "Control Plane Pathが不正です: " + exception.Message;
                return false;
            }

            if (!File.Exists(fullPath))
            {
                error = "選択したUnityAgent Control Planeが存在しません: " + fullPath;
                return false;
            }

            EditorPrefs.SetString(EditorPrefKey, fullPath);
            return true;
        }

        internal static void ClearOverride()
        {
            EditorPrefs.DeleteKey(EditorPrefKey);
        }

        internal static string Resolve(out string source, out string diagnostic)
        {
            source = string.Empty;
            diagnostic = string.Empty;

            if (HasOverride)
            {
                var overridePath = GetOverride();
                if (File.Exists(overridePath))
                {
                    source = "Manual override";
                    return Path.GetFullPath(overridePath);
                }

                source = "Manual override";
                diagnostic = "保存されたControl Plane Pathが存在しません。『Override解除』または『参照...』を使用してください。";
                return null;
            }

            foreach (var candidate in EnumerateCandidates())
            {
                if (string.IsNullOrWhiteSpace(candidate.Path) || !File.Exists(candidate.Path))
                {
                    continue;
                }

                source = candidate.Source;
                return Path.GetFullPath(candidate.Path);
            }

            diagnostic =
                "UnityAgent Control Planeを検出できませんでした。User環境変数、User PATH、Python User Scripts、現在のPATHを確認しました。";
            return null;
        }

        private static IEnumerable<(string Path, string Source)> EnumerateCandidates()
        {
            foreach (var candidate in EnvironmentCandidates())
            {
                yield return candidate;
            }

            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                foreach (var candidate in WindowsPythonCandidates())
                {
                    yield return candidate;
                }
            }
            else
            {
                var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(home))
                {
                    yield return (Path.Combine(home, ".local", "bin", "unity-agent"), "User local bin");
                }
                yield return ("/usr/local/bin/unity-agent", "Common system location");
                yield return ("/usr/bin/unity-agent", "Common system location");
            }

            foreach (var candidate in EnumeratePathCandidates(Environment.GetEnvironmentVariable("PATH"), "Process PATH"))
            {
                yield return candidate;
            }

            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                string userPath = null;
                try
                {
                    userPath = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.User);
                }
                catch
                {
                    // Best-effort only.
                }

                foreach (var candidate in EnumeratePathCandidates(userPath, "User PATH"))
                {
                    yield return candidate;
                }
            }
        }

        private static IEnumerable<(string Path, string Source)> EnvironmentCandidates()
        {
            var processValue = Environment.GetEnvironmentVariable(EnvironmentVariable);
            if (!string.IsNullOrWhiteSpace(processValue))
            {
                yield return (processValue.Trim(), "Environment: " + EnvironmentVariable);
            }

            if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                yield break;
            }

            string userValue = null;
            try
            {
                userValue = Environment.GetEnvironmentVariable(EnvironmentVariable, EnvironmentVariableTarget.User);
            }
            catch
            {
                // Best-effort only.
            }

            if (!string.IsNullOrWhiteSpace(userValue))
            {
                yield return (userValue.Trim(), "User environment: " + EnvironmentVariable);
            }
        }

        private static IEnumerable<(string Path, string Source)> WindowsPythonCandidates()
        {
            var userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) ?? string.Empty;
            var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) ?? string.Empty;
            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) ?? string.Empty;

            foreach (var root in new[]
                     {
                         string.IsNullOrWhiteSpace(appData) ? null : Path.Combine(appData, "Python"),
                         string.IsNullOrWhiteSpace(userProfile) ? null : Path.Combine(userProfile, "AppData", "Roaming", "Python"),
                         string.IsNullOrWhiteSpace(localAppData) ? null : Path.Combine(localAppData, "Programs", "Python"),
                     }.Where(value => !string.IsNullOrWhiteSpace(value)))
            {
                if (!Directory.Exists(root))
                {
                    continue;
                }

                IEnumerable<string> versionDirectories;
                try
                {
                    versionDirectories = Directory.EnumerateDirectories(root)
                        .OrderByDescending(path => path, StringComparer.OrdinalIgnoreCase)
                        .ToArray();
                }
                catch
                {
                    continue;
                }

                foreach (var versionDirectory in versionDirectories)
                {
                    foreach (var fileName in WindowsExecutableNames())
                    {
                        yield return (
                            Path.Combine(versionDirectory, "Scripts", fileName),
                            "Python User Scripts");
                    }
                }
            }

            if (!string.IsNullOrWhiteSpace(userProfile))
            {
                foreach (var fileName in WindowsExecutableNames())
                {
                    yield return (Path.Combine(userProfile, ".local", "bin", fileName), "User local bin");
                }
            }
        }

        private static IEnumerable<(string Path, string Source)> EnumeratePathCandidates(string pathValue, string source)
        {
            if (string.IsNullOrWhiteSpace(pathValue))
            {
                yield break;
            }

            foreach (var rawDirectory in pathValue.Split(Path.PathSeparator))
            {
                if (string.IsNullOrWhiteSpace(rawDirectory))
                {
                    continue;
                }

                var directory = rawDirectory.Trim().Trim('"');
                if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                {
                    foreach (var fileName in WindowsExecutableNames())
                    {
                        yield return (Path.Combine(directory, fileName), source);
                    }
                }
                else
                {
                    yield return (Path.Combine(directory, "unity-agent"), source);
                }
            }
        }

        private static IEnumerable<string> WindowsExecutableNames()
        {
            yield return "unity-agent.exe";
            yield return "unity-agent.cmd";
            yield return "unity-agent.bat";
            yield return "unity-agent";
        }
    }
}
