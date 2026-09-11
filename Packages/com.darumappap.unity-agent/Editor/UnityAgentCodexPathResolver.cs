using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using UnityEditor;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// Resolves the Codex Local runtime without relying only on the PATH inherited by Unity Hub.
    /// Discovery is intentionally read-only. Executable validation belongs to the
    /// Control Plane / Installer Provider so the Entry Layer never executes Codex directly.
    /// </summary>
    internal static class UnityAgentCodexPathResolver
    {
        internal const string EditorPrefKey = "DarumaPPAP.UnityAgent.CodexCliPath";

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

            var fullPath = Path.GetFullPath(path.Trim());
            if (!File.Exists(fullPath))
            {
                error = "選択したCodex Local runtimeが存在しません: " + fullPath;
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
                    source = IsDesktopManagedRuntime(overridePath) ? "Codex Desktop managed runtime" : "Manual override";
                    return Path.GetFullPath(overridePath);
                }

                source = "Manual override";
                diagnostic = "保存されたCodex Local runtime Pathが無効です。『Override解除』または『参照...』を使用してください。";
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

            diagnostic = "Codex Local runtimeを検出できませんでした。Codex Desktop managed runtime、PATH、npm/NVMの一般的な配置先、環境変数を確認しました。";
            return null;
        }

        internal static bool IsDesktopManagedRuntime(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return false;
            }

            var normalized = path.Replace('/', '\\');
            return normalized.IndexOf("\\.codex\\packages\\standalone\\releases\\", StringComparison.OrdinalIgnoreCase) >= 0 ||
                   normalized.IndexOf("\\Programs\\OpenAI\\Codex\\", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static IEnumerable<(string Path, string Source)> EnumerateCandidates()
        {
            foreach (var environmentVariable in new[] { "UNITY_AGENT_CODEX_CLI", "CODEX_CLI" })
            {
                var value = Environment.GetEnvironmentVariable(environmentVariable);
                if (!string.IsNullOrWhiteSpace(value))
                {
                    yield return (value.Trim(), "Environment: " + environmentVariable);
                }
            }

            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) ?? string.Empty;
                var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) ?? string.Empty;
                var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) ?? string.Empty;
                var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles) ?? string.Empty;
                var nvmSymlink = Environment.GetEnvironmentVariable("NVM_SYMLINK") ?? string.Empty;

                foreach (var candidate in WindowsDesktopRuntimeCandidates(home, localAppData))
                {
                    yield return candidate;
                }

                foreach (var path in WindowsCandidates(appData, localAppData, home, programFiles, nvmSymlink))
                {
                    yield return (path, "Common Windows location");
                }

                foreach (var pathCandidate in EnumerateWindowsPathCandidates())
                {
                    yield return (pathCandidate, "PATH");
                }
                yield break;
            }

            var userHome = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) ?? string.Empty;
            if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
            {
                yield return ("/opt/homebrew/bin/codex", "Homebrew");
                yield return ("/usr/local/bin/codex", "Common macOS location");
            }
            else
            {
                yield return ("/usr/local/bin/codex", "Common Linux location");
                yield return ("/usr/bin/codex", "Common Linux location");
            }

            if (!string.IsNullOrWhiteSpace(userHome))
            {
                yield return (Path.Combine(userHome, ".local", "bin", "codex"), "User local bin");
                yield return (Path.Combine(userHome, ".npm-global", "bin", "codex"), "npm global");
                foreach (var nvmCandidate in EnumerateNvmCandidates(userHome))
                {
                    yield return (nvmCandidate, "NVM");
                }
            }

            foreach (var pathCandidate in EnumeratePathCandidates("codex"))
            {
                yield return (pathCandidate, "PATH");
            }
        }

        private static IEnumerable<(string Path, string Source)> WindowsDesktopRuntimeCandidates(string home, string localAppData)
        {
            if (!string.IsNullOrWhiteSpace(localAppData))
            {
                var appBin = Path.Combine(localAppData, "Programs", "OpenAI", "Codex", "bin");
                foreach (var fileName in WindowsExecutableNames())
                {
                    yield return (Path.Combine(appBin, fileName), "Codex Desktop installation");
                }
            }

            if (string.IsNullOrWhiteSpace(home))
            {
                yield break;
            }

            var releasesRoot = Path.Combine(home, ".codex", "packages", "standalone", "releases");
            if (!Directory.Exists(releasesRoot))
            {
                yield break;
            }

            IEnumerable<string> releases;
            try
            {
                releases = Directory.EnumerateDirectories(releasesRoot)
                    .OrderByDescending(path => path, StringComparer.OrdinalIgnoreCase)
                    .ToArray();
            }
            catch
            {
                yield break;
            }

            foreach (var release in releases)
            {
                foreach (var fileName in WindowsExecutableNames())
                {
                    yield return (Path.Combine(release, "bin", fileName), "Codex Desktop managed runtime");
                }
            }
        }

        private static IEnumerable<string> WindowsCandidates(
            string appData,
            string localAppData,
            string home,
            string programFiles,
            string nvmSymlink)
        {
            foreach (var root in new[]
                     {
                         string.IsNullOrWhiteSpace(appData) ? null : Path.Combine(appData, "npm"),
                         string.IsNullOrWhiteSpace(localAppData) ? null : Path.Combine(localAppData, "npm"),
                         string.IsNullOrWhiteSpace(localAppData) ? null : Path.Combine(localAppData, "Programs", "codex"),
                         string.IsNullOrWhiteSpace(home) ? null : Path.Combine(home, ".local", "bin"),
                         string.IsNullOrWhiteSpace(home) ? null : Path.Combine(home, ".npm-global", "bin"),
                         string.IsNullOrWhiteSpace(programFiles) ? null : Path.Combine(programFiles, "nodejs"),
                         string.IsNullOrWhiteSpace(nvmSymlink) ? null : nvmSymlink,
                     }.Where(value => !string.IsNullOrWhiteSpace(value)))
            {
                foreach (var fileName in WindowsExecutableNames())
                {
                    yield return Path.Combine(root, fileName);
                }
            }
        }

        private static IEnumerable<string> EnumerateNvmCandidates(string home)
        {
            var root = Path.Combine(home, ".nvm", "versions", "node");
            if (!Directory.Exists(root))
            {
                yield break;
            }

            foreach (var versionDirectory in Directory.EnumerateDirectories(root).OrderByDescending(path => path))
            {
                yield return Path.Combine(versionDirectory, "bin", "codex");
            }
        }

        private static IEnumerable<string> EnumerateWindowsPathCandidates()
        {
            var path = Environment.GetEnvironmentVariable("PATH");
            if (string.IsNullOrWhiteSpace(path))
            {
                yield break;
            }

            foreach (var rawDirectory in path.Split(Path.PathSeparator))
            {
                if (string.IsNullOrWhiteSpace(rawDirectory))
                {
                    continue;
                }

                var directory = rawDirectory.Trim();
                foreach (var fileName in WindowsExecutableNames())
                {
                    yield return Path.Combine(directory, fileName);
                }
            }
        }

        private static IEnumerable<string> EnumeratePathCandidates(string executable)
        {
            var path = Environment.GetEnvironmentVariable("PATH");
            if (string.IsNullOrWhiteSpace(path))
            {
                yield break;
            }

            foreach (var rawDirectory in path.Split(Path.PathSeparator))
            {
                if (!string.IsNullOrWhiteSpace(rawDirectory))
                {
                    yield return Path.Combine(rawDirectory.Trim(), executable);
                }
            }
        }

        private static IEnumerable<string> WindowsExecutableNames()
        {
            yield return "codex.exe";
            yield return "codex.cmd";
            yield return "codex.bat";
            yield return "codex.ps1";
            yield return "codex";
        }
    }
}
