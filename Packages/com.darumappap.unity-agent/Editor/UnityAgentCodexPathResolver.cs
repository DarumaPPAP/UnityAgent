using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using UnityEditor;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// Resolves and validates the Codex CLI without relying only on the PATH inherited by Unity Hub.
    /// The resolution order intentionally mirrors the robust client discovery pattern used by MCP for Unity:
    /// explicit EditorPrefs override -> environment hints -> common install locations -> NVM/npm -> PATH/where.
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
                error = "選択したCodex CLIが存在しません: " + fullPath;
                return false;
            }

            if (!TryValidate(fullPath, out var version, out var validationError))
            {
                error = "選択したファイルをCodex CLIとして実行できません。\n" + validationError;
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
                if (File.Exists(overridePath) && TryValidate(overridePath, out _, out diagnostic))
                {
                    source = "Manual override";
                    diagnostic = string.Empty;
                    return overridePath;
                }

                source = "Manual override";
                diagnostic = string.IsNullOrWhiteSpace(diagnostic)
                    ? "保存されたCodex CLI Pathが無効です。『Override解除』または『参照...』を使用してください。"
                    : diagnostic;
                return null;
            }

            foreach (var candidate in EnumerateCandidates())
            {
                if (string.IsNullOrWhiteSpace(candidate.Path) || !File.Exists(candidate.Path))
                {
                    continue;
                }

                if (!TryValidate(candidate.Path, out _, out _))
                {
                    continue;
                }

                source = candidate.Source;
                return Path.GetFullPath(candidate.Path);
            }

            diagnostic =
                "Codex CLIを検出できませんでした。PATH、npm/NVMの一般的な配置先、環境変数を確認しました。";
            return null;
        }

        internal static bool TryValidate(string path, out string version, out string error)
        {
            version = string.Empty;
            error = string.Empty;
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            {
                error = "ファイルが存在しません: " + path;
                return false;
            }

            try
            {
                var startInfo = BuildVersionProcess(path);
                using (var process = new Process { StartInfo = startInfo })
                {
                    var stdout = new StringBuilder();
                    var stderr = new StringBuilder();
                    process.OutputDataReceived += (_, e) => { if (e.Data != null) stdout.AppendLine(e.Data); };
                    process.ErrorDataReceived += (_, e) => { if (e.Data != null) stderr.AppendLine(e.Data); };

                    if (!process.Start())
                    {
                        error = "Codex CLI processを起動できませんでした。";
                        return false;
                    }
                    process.BeginOutputReadLine();
                    process.BeginErrorReadLine();
                    if (!process.WaitForExit(5000))
                    {
                        try { process.Kill(); } catch { }
                        error = "codex --version が5秒以内に完了しませんでした。";
                        return false;
                    }
                    process.WaitForExit();

                    var versionText = !string.IsNullOrWhiteSpace(stdout.ToString())
                        ? stdout.ToString().Trim()
                        : stderr.ToString().Trim();
                    if (process.ExitCode != 0)
                    {
                        error = "codex --version が失敗しました。 ExitCode=" + process.ExitCode +
                                (string.IsNullOrWhiteSpace(versionText) ? string.Empty : "\n" + versionText);
                        return false;
                    }

                    version = versionText;
                    return true;
                }
            }
            catch (Exception exception)
            {
                error = exception.GetType().Name + ": " + exception.Message;
                return false;
            }
        }

        private static ProcessStartInfo BuildVersionProcess(string path)
        {
            var extension = Path.GetExtension(path).ToLowerInvariant();
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows) && (extension == ".cmd" || extension == ".bat"))
            {
                var commandInterpreter = Environment.GetEnvironmentVariable("COMSPEC");
                if (string.IsNullOrWhiteSpace(commandInterpreter))
                {
                    commandInterpreter = "cmd.exe";
                }
                return CreateStartInfo(
                    commandInterpreter,
                    "/d /s /c \"\"" + path.Replace("\"", "\\\"") + "\" --version\"");
            }

            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows) && extension == ".ps1")
            {
                return CreateStartInfo(
                    "powershell.exe",
                    "-NoProfile -ExecutionPolicy Bypass -File \"" + path.Replace("\"", "\\\"") + "\" --version");
            }

            return CreateStartInfo(path, "--version");
        }

        private static ProcessStartInfo CreateStartInfo(string fileName, string arguments)
        {
            return new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };
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

                foreach (var path in WindowsCandidates(appData, localAppData, home, programFiles, nvmSymlink))
                {
                    yield return (path, "Common Windows location");
                }

                var fromWhere = FindInPathWindows();
                if (!string.IsNullOrWhiteSpace(fromWhere))
                {
                    yield return (fromWhere, "PATH / where.exe");
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

            foreach (var pathCandidate in EnumeratePathDirectories("codex"))
            {
                yield return (pathCandidate, "PATH");
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
                         string.IsNullOrWhiteSpace(home) ? null : Path.Combine(home, ".npm-global"),
                         string.IsNullOrWhiteSpace(programFiles) ? null : Path.Combine(programFiles, "nodejs"),
                         string.IsNullOrWhiteSpace(nvmSymlink) ? null : nvmSymlink,
                     }.Where(value => !string.IsNullOrWhiteSpace(value)))
            {
                foreach (var fileName in new[] { "codex.cmd", "codex.exe", "codex.bat", "codex.ps1", "codex" })
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

        private static IEnumerable<string> EnumeratePathDirectories(string executable)
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

        private static string FindInPathWindows()
        {
            try
            {
                var startInfo = CreateStartInfo("where.exe", "codex");
                using (var process = new Process { StartInfo = startInfo })
                {
                    if (!process.Start())
                    {
                        return null;
                    }
                    var output = process.StandardOutput.ReadToEnd();
                    process.WaitForExit(1500);
                    if (!process.HasExited || process.ExitCode != 0)
                    {
                        try { process.Kill(); } catch { }
                        return null;
                    }
                    return output
                        .Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
                        .FirstOrDefault(File.Exists);
                }
            }
            catch
            {
                return null;
            }
        }
    }
}
