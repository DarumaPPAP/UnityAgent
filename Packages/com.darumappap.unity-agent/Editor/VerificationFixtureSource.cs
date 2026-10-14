using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// UnityAgent UPM同梱のP9 Inputがビルド時Manifestと一致することを確認する。
    /// 元ソースはUnityAgent/ciとPackages/Artist、UPMだけに作業用Mirrorを作る。
    /// </summary>
    internal sealed class VerificationFixtureSource
    {
        [Serializable]
        private sealed class Manifest
        {
            public string schema_version;
            public string kind;
            public ManifestEntry[] files;
        }

        [Serializable]
        private sealed class ManifestEntry
        {
            public string path;
            public string sha1;
            public long size;
        }

        private readonly string _root;
        private readonly string _error;

        internal VerificationFixtureSource()
        {
            var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(
                typeof(VerificationFixtureSource).Assembly);
            if (package == null || string.IsNullOrWhiteSpace(package.resolvedPath))
            {
                _error = "UnityAgent UPMが見つかりません。";
                return;
            }
            _root = Path.Combine(package.resolvedPath, "Editor", "Verification~");
        }

        internal bool TryGetVerifiedSource(out string root, out string reason)
        {
            root = string.Empty;
            reason = _error ?? string.Empty;
            if (!string.IsNullOrEmpty(reason))
            {
                return false;
            }
            try
            {
                if (string.IsNullOrEmpty(_root) || !Directory.Exists(_root) || IsLink(_root))
                {
                    reason = "UPM同梱の検証フォルダが存在しない、またはリンクです。";
                    return false;
                }
                var input = Path.Combine(_root, "p9-source-manifest.json");
                if (!File.Exists(input) || IsLink(input))
                {
                    reason = "P9検証用Manifestが存在しません。";
                    return false;
                }
                var payload = JsonUtility.FromJson<Manifest>(File.ReadAllText(input, Encoding.UTF8));
                if (payload == null || payload.schema_version != "1.0" ||
                    payload.kind != "unityagent_embedded_p9_sources" ||
                    payload.files == null || payload.files.Length < 1)
                {
                    reason = "P9検証用Manifestの形式が正しくありません。";
                    return false;
                }
                var expected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (var entry in payload.files)
                {
                    if (entry == null || string.IsNullOrWhiteSpace(entry.path) ||
                        entry.path.IndexOf('\\') >= 0 ||
                        !Regex.IsMatch(entry.path, @"^[A-Za-z0-9_.\-/]+$") ||
                        entry.path.Split('/').Length < 2 ||
                        Array.Exists(entry.path.Split('/'), part => part == "." || part == "..") ||
                        !Regex.IsMatch(entry.sha1 ?? "", "^[0-9a-f]{40}$") ||
                        entry.size < 0 || !expected.Add(entry.path))
                    {
                        reason = "P9検証Manifestに不正・重複Pathがあります。";
                        return false;
                    }
                    var path = Path.Combine(_root, entry.path.Replace('/', Path.DirectorySeparatorChar));
                    var current = Path.GetFullPath(path);
                    var trusted = Path.GetFullPath(_root).TrimEnd(Path.DirectorySeparatorChar) +
                        Path.DirectorySeparatorChar;
                    if (!current.StartsWith(trusted, StringComparison.OrdinalIgnoreCase) ||
                        !File.Exists(current) || new FileInfo(current).Length != entry.size ||
                        ContainsLinkBetween(current, _root) ||
                        !string.Equals(GitObjectHash(current), entry.sha1, StringComparison.Ordinal))
                    {
                        reason = "P9検証Sourceが欠損・改変されています: " + entry.path;
                        return false;
                    }
                }
                // 未登録ファイルによるPython module shadowing / スクリプト差し替えを拒否する。
                foreach (var file in Directory.GetFiles(_root, "*", SearchOption.AllDirectories))
                {
                    var relative = file.Substring(_root.Length).TrimStart(Path.DirectorySeparatorChar)
                        .Replace(Path.DirectorySeparatorChar, '/');
                    if (relative != "p9-source-manifest.json" && !expected.Contains(relative))
                    {
                        reason = "P9検証フォルダに未登録ファイルがあります: " + relative;
                        return false;
                    }
                }
                root = _root;
                return true;
            }
            catch (Exception exception)
            {
                reason = "UPM同梱のP9検証Source確認に失敗: " + exception.Message;
                return false;
            }
        }

        private static bool ContainsLinkBetween(string path, string root)
        {
            var current = new FileInfo(path);
            var directory = current.Directory;
            if (IsLink(current.FullName))
            {
                return true;
            }
            while (directory != null)
            {
                if (IsLink(directory.FullName))
                {
                    return true;
                }
                if (string.Equals(directory.FullName, root, StringComparison.OrdinalIgnoreCase))
                {
                    return false;
                }
                directory = directory.Parent;
            }
            return true;
        }

        private static bool IsLink(string path)
        {
            return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
        }

        // GitHub Source Treeのblob IDをFile bytesから検証する。UPM Git sourceとの同一性検査。
        private static string GitObjectHash(string path)
        {
            var bytes = File.ReadAllBytes(path);
            var header = Encoding.ASCII.GetBytes("blob " + bytes.Length + "\0");
            var content = new byte[header.Length + bytes.Length];
            Buffer.BlockCopy(header, 0, content, 0, header.Length);
            Buffer.BlockCopy(bytes, 0, content, header.Length, bytes.Length);
            using (var sha1 = SHA1.Create())
            {
                var digest = sha1.ComputeHash(content);
                return BitConverter.ToString(digest).Replace("-", "").ToLowerInvariant();
            }
        }
    }
}
