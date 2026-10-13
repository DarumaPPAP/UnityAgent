using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// Source Lockの固定CommitだけをUnityAgent管理キャッシュに取得する。
    /// Unity Editorプロセス外でのGit操作だけを担当し、HubはRuntime/Routerにしない。
    /// </summary>
    internal sealed class VerificationHubSource
    {
        private const string ExpectedRepository = "DarumaPPAP/UnitySubAgentHub";
        private const string GitRemote = "https://github.com/DarumaPPAP/UnitySubAgentHub.git";

        [Serializable]
        private sealed class LockRecord
        {
            public HubRecord hub;
        }

        [Serializable]
        private sealed class HubRecord
        {
            public string repository;
            public string commit;
        }

        internal string Commit { get; private set; }
        internal string Error { get; private set; }
        internal string CacheDirectory { get; private set; }

        internal VerificationHubSource()
        {
            Error = string.Empty;
            var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(typeof(VerificationHubSource).Assembly);
            if (package == null || string.IsNullOrWhiteSpace(package.resolvedPath))
            {
                Error = "UnityAgent UPMのPathを解決できません。";
                return;
            }
            var path = Path.Combine(package.resolvedPath, "Editor", "Verification~", "subagent-sources.lock.json");
            if (!File.Exists(path))
            {
                Error = "UPMに検証用Source Lockがありません。UnityAgentを更新してください。";
                return;
            }
            try
            {
                var record = JsonUtility.FromJson<LockRecord>(File.ReadAllText(path, Encoding.UTF8));
                if (record == null || record.hub == null ||
                    record.hub.repository != ExpectedRepository ||
                    string.IsNullOrWhiteSpace(record.hub.commit) ||
                    !Regex.IsMatch(record.hub.commit, "^[a-f0-9]{40}$"))
                {
                    Error = "Hub Source Lockの形式が正しくありません。";
                    return;
                }
                Commit = record.hub.commit;
                var root = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                if (string.IsNullOrWhiteSpace(root))
                {
                    Error = "LocalAppDataを解決できません。";
                    return;
                }
                CacheDirectory = Path.Combine(root, "UnityAgent", "VerificationHub", Commit);
            }
            catch (Exception exception)
            {
                Error = "Hub Source Lockの解析に失敗しました: " + exception.Message;
            }
        }

        internal bool TryGetVerifiedCache(out string root, out string reason)
        {
            root = string.Empty;
            reason = Error;
            if (!string.IsNullOrWhiteSpace(reason))
            {
                return false;
            }
            if (string.IsNullOrWhiteSpace(CacheDirectory) || !Directory.Exists(CacheDirectory))
            {
                reason = "Hub検証環境は未取得です。";
                return false;
            }
            if (IsReparsePoint(CacheDirectory))
            {
                reason = "Hub検証キャッシュが不正です（リンクを検出）。";
                return false;
            }
            try
            {
                var resolved = Git("-C " + Quote(CacheDirectory) + " rev-parse HEAD", CacheDirectory);
                if (!string.Equals(resolved.Trim(), Commit, StringComparison.Ordinal))
                {
                    reason = "キャッシュのCommitがSource Lockと一致しません。";
                    return false;
                }
                if (!string.IsNullOrWhiteSpace(Git("-C " + Quote(CacheDirectory) +
                    " status --porcelain --untracked-files=all", CacheDirectory)))
                {
                    reason = "キャッシュに未Commit変更があります。実行を停止します。";
                    return false;
                }
                var required = new[]
                {
                    "ci/scripts/run-unity-tests.ps1",
                    "ci/unity-matrix.yaml",
                    "ci/verify/unity_ci.py",
                    "Hub/Registry/subagents.yaml",
                    "Packages/com.darumappap.artist-subagent/package.json",
                };
                foreach (var relative in required)
                {
                    if (!File.Exists(Path.Combine(CacheDirectory, relative.Replace('/', Path.DirectorySeparatorChar))))
                    {
                        reason = "Hub検証環境の必須ファイルがありません: " + relative;
                        return false;
                    }
                }
                root = CacheDirectory;
                reason = string.Empty;
                return true;
            }
            catch (Exception exception)
            {
                reason = "Hub検証環境の検証に失敗しました: " + exception.Message;
                return false;
            }
        }

        internal string Prepare()
        {
            if (!string.IsNullOrWhiteSpace(Error))
            {
                return Error;
            }
            if (TryGetVerifiedCache(out _, out _))
            {
                return string.Empty;
            }
            // 壊れたキャッシュを上書き/削除せず、原因を報告して停止する。
            if (Directory.Exists(CacheDirectory))
            {
                return "既存の検証キャッシュが不正です。安全のため自動削除しません。";
            }

            var parent = Path.GetDirectoryName(CacheDirectory);
            if (string.IsNullOrEmpty(parent))
            {
                return "検証キャッシュの保存先が不正です。";
            }
            Directory.CreateDirectory(parent);
            var stage = Path.Combine(parent, ".staging-" + Guid.NewGuid().ToString("N"));
            try
            {
                Directory.CreateDirectory(stage);
                Git("init -q " + Quote(stage), parent);
                Git("-C " + Quote(stage) + " remote add origin " + GitRemote, parent);
                // GitHubの公開mainでなく、UPMが承認したHub SHAだけを取得する。
                Git("-C " + Quote(stage) + " fetch --no-tags --depth 1 origin " + Commit, parent);
                var fetched = Git("-C " + Quote(stage) + " rev-parse FETCH_HEAD", parent);
                if (fetched.Trim() != Commit)
                {
                    return "取得したHubのCommitが固定Source Lockと異なります。";
                }
                Git("-C " + Quote(stage) + " -c core.symlinks=false checkout --detach FETCH_HEAD", parent);
                // P9ソースの配置が期待と異なれば実行しない。
                var runner = Path.Combine(stage, "ci", "scripts", "run-unity-tests.ps1");
                if (!File.Exists(runner))
                {
                    return "PinされたHubコミットにP9 Runnerがありません。";
                }
                if (Directory.Exists(CacheDirectory))
                {
                    return "別処理が検証キャッシュを更新しました。再検証してください。";
                }
                Directory.Move(stage, CacheDirectory);
                return TryGetVerifiedCache(out _, out var check) ? string.Empty : check;
            }
            catch (Exception exception)
            {
                return "検証環境の取得に失敗しました（Git接続・権限・インストールを確認）: " +
                    exception.Message;
            }
            finally
            {
                if (Directory.Exists(stage))
                {
                    try { Directory.Delete(stage, true); }
                    catch (IOException) { }
                    catch (UnauthorizedAccessException) { }
                }
            }
        }

        private static bool IsReparsePoint(string path)
        {
            return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
        }

        private static string Git(string arguments, string workingDirectory)
        {
            var start = new ProcessStartInfo
            {
                FileName = "git.exe",
                Arguments = arguments,
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using (var process = new Process { StartInfo = start })
            {
                var stdout = new StringBuilder();
                var stderr = new StringBuilder();
                process.OutputDataReceived += (_, args) =>
                {
                    if (args.Data != null) stdout.AppendLine(args.Data);
                };
                process.ErrorDataReceived += (_, args) =>
                {
                    if (args.Data != null) stderr.AppendLine(args.Data);
                };
                if (!process.Start())
                {
                    throw new IOException("Gitを起動できません。");
                }
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                if (!process.WaitForExit(180000))
                {
                    try { process.Kill(); } catch (InvalidOperationException) { }
                    throw new TimeoutException("Git処理が180秒以内に完了しませんでした。");
                }
                process.WaitForExit();
                if (process.ExitCode != 0)
                {
                    throw new IOException("Git exited " + process.ExitCode + ": " + stderr);
                }
                return stdout.ToString().Trim();
            }
        }

        private static string Quote(string value)
        {
            if (string.IsNullOrEmpty(value) || value.IndexOf('"') >= 0 ||
                value.IndexOf('\r') >= 0 || value.IndexOf('\n') >= 0)
            {
                throw new ArgumentException("検証環境Pathに使用できない文字が含まれています。");
            }
            return "\"" + value + "\"";
        }
    }
}
