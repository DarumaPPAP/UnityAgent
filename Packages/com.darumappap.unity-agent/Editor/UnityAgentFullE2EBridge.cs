using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace DarumaPPAP.UnityAgent.Editor
{
    // 固定の操作だけを受け付け、任意のEditor API・Path・C# source・YAMLは実行しない。
    [InitializeOnLoad]
    internal static class UnityAgentFullE2EBridge
    {
        private const string AssetDirectory = "Assets/UnityAgentE2E";
        private const string ScenePath = AssetDirectory + "/FullE2EScene.unity";
        private const string MaterialPath = AssetDirectory + "/FullE2EMaterial.mat";
        private const string ScriptPath = AssetDirectory + "/FullE2EProbe.cs";
        private const string ObjectName = "FullE2EProbeCube";
        private const string TemplatePath = "Packages/com.darumappap.unity-agent/Editor/Resources/FullE2EProbe.txt";
        private static readonly string[] ExpectedPaths =
        {
            AssetDirectory + ".meta", ScenePath, ScenePath + ".meta",
            MaterialPath, MaterialPath + ".meta", ScriptPath, ScriptPath + ".meta",
        };

        [Serializable]
        private sealed class Ticket
        {
            public string schema_version;
            public string run_id;
            public string project_root;
            public string plan_id;
            public string approval_ref;
            public string save_approval_ref;
            public string expires_at;
            public string script_sha256;
            public string instance_id;
            public string state_root;
            public string plan_digest;
            public string mutation_decision_digest;
            public string save_decision_digest;
            public string signature;
        }

        [Serializable]
        private sealed class ApprovalRecord
        {
            public string schema_version;
            public ApprovalValue decision;
            public int current_revocation_epoch;
        }

        [Serializable]
        private sealed class ApprovalValue
        {
            public string approval_decision_id;
            public string approval_kind;
            public string plan_id;
            public string project_root;
            public string plan_digest;
            public string[] scope_paths;
            public string human_review;
            public string status;
            public string expires_at;
            public int revocation_epoch;
            public string decision_digest;
        }

        [Serializable]
        private sealed class ActiveJob
        {
            public Ticket ticket;
            public string phase;
            public string previous_scene_path;
            public string compile;
            public string playmode;
            public string failure_reason;
            public string import_started_at;
        }

        [Serializable]
        private sealed class EditorResult
        {
            public string schema_version = "1.0";
            public string run_id;
            public string project_root;
            public string plan_id;
            public string approval_ref;
            public string save_approval_ref;
            public string status;
            public string compile;
            public string playmode;
            public string script_sha256;
            public string object_name = ObjectName;
            public string instance_id;
            public string shader_name;
            public string[] changed_paths;
            public string reason;
            public string signature;
        }

        [Serializable]
        private sealed class Heartbeat
        {
            public string schema_version = "1.0";
            public string project_root;
            public string editor_version;
            public string editor_path;
            public int process_id;
            public string instance_id;
            public bool safe_mode;
            public string updated_at;
        }

        [Serializable]
        private sealed class EditorSession
        {
            public int process_id;
            public string process_started_at;
            public string instance_id;
        }

        private static readonly string ProjectRoot = Directory.GetParent(Application.dataPath).FullName;
        private static readonly string BridgeRoot = Path.Combine(ProjectRoot, "Library/UnityAgent/full_e2e");
        private static readonly string ActivePath = Path.Combine(BridgeRoot, "active.json");
        private static readonly string KeyPath = Path.Combine(BridgeRoot, "bridge.key");
        private static readonly string InstanceId = ResolveInstanceId();
        private static double _lastHeartbeat;

        static UnityAgentFullE2EBridge()
        {
            EditorApplication.update += Tick;
        }

        private static string ResolveInstanceId()
        {
            Directory.CreateDirectory(BridgeRoot);
            var process = System.Diagnostics.Process.GetCurrentProcess();
            var currentPid = process.Id;
            var startedAt = process.StartTime.ToUniversalTime().ToString("o");
            var path = Path.Combine(BridgeRoot, "session.json");
            if (File.Exists(path))
            {
                try
                {
                    var previous = JsonUtility.FromJson<EditorSession>(File.ReadAllText(path));
                    if (previous != null && previous.process_id == currentPid &&
                        previous.process_started_at == startedAt && !string.IsNullOrEmpty(previous.instance_id))
                    {
                        return previous.instance_id;
                    }
                }
                catch (Exception)
                {
                    // 破損したSessionは再利用せず、新しいEditor instanceとして発行する。
                }
            }
            var session = new EditorSession { process_id = currentPid, process_started_at = startedAt,
                instance_id = Guid.NewGuid().ToString("N") };
            AtomicJson(path, session);
            return session.instance_id;
        }

        private static void Tick()
        {
            try
            {
                EnsureKey();
                if (EditorApplication.timeSinceStartup - _lastHeartbeat > 1)
                {
                    WriteHeartbeat();
                    _lastHeartbeat = EditorApplication.timeSinceStartup;
                }
                if (File.Exists(ActivePath))
                {
                    var active = JsonUtility.FromJson<ActiveJob>(File.ReadAllText(ActivePath));
                    // Domain reload後も署名付きTicketを再確認し、active.json単体に権限を与えない。
                    if (active == null || !ValidTicketIdentity(active.ticket))
                    {
                        File.Delete(ActivePath);
                        if (EditorApplication.isPlaying) EditorApplication.ExitPlaymode();
                        Debug.LogError("UnityAgent Full E2E bridge rejected an unbound active job");
                        return;
                    }
                    Advance(active);
                }
                else if (!EditorApplication.isPlayingOrWillChangePlaymode && !EditorApplication.isCompiling)
                {
                    BeginNext();
                }
            }
            catch (Exception exception)
            {
                Debug.LogError("UnityAgent Full E2E bridge: " + exception);
                if (File.Exists(ActivePath))
                {
                    try
                    {
                        var active = JsonUtility.FromJson<ActiveJob>(File.ReadAllText(ActivePath));
                        active.failure_reason = exception.Message;
                        active.phase = "exit";
                        Save(active);
                        if (EditorApplication.isPlaying) EditorApplication.ExitPlaymode();
                    }
                    catch (Exception nested)
                    {
                        Debug.LogError("UnityAgent Full E2E bridge could not persist failure: " + nested);
                    }
                }
            }
        }

        private static void EnsureKey()
        {
            if (File.Exists(KeyPath)) return;
            var bytes = new byte[32];
            using (var generator = RandomNumberGenerator.Create()) generator.GetBytes(bytes);
            File.WriteAllText(KeyPath, Convert.ToBase64String(bytes), Encoding.ASCII);
        }

        private static byte[] Secret()
        {
            return Convert.FromBase64String(File.ReadAllText(KeyPath, Encoding.ASCII));
        }

        private static string Hmac(string message)
        {
            using (var digest = new HMACSHA256(Secret()))
            {
                return BitConverter.ToString(digest.ComputeHash(Encoding.UTF8.GetBytes(message))).Replace("-", "").ToLowerInvariant();
            }
        }

        private static bool Matches(string expected, string observed)
        {
            if (expected == null || observed == null || expected.Length != observed.Length) return false;
            var difference = 0;
            for (var index = 0; index < expected.Length; index++) difference |= expected[index] ^ observed[index];
            return difference == 0;
        }

        private static string JobMessage(Ticket ticket)
        {
            return string.Join("\n", new[] { ticket.run_id, ticket.project_root, ticket.plan_id,
                ticket.approval_ref, ticket.save_approval_ref, ticket.expires_at, ticket.script_sha256, ticket.instance_id,
                ticket.state_root, ticket.plan_digest, ticket.mutation_decision_digest, ticket.save_decision_digest });
        }

        private static string ResultMessage(EditorResult result)
        {
            return string.Join("\n", new[] { result.run_id, result.project_root, result.plan_id,
                result.approval_ref, result.save_approval_ref, result.status, result.compile,
                result.playmode, result.script_sha256, result.object_name, result.instance_id, result.shader_name,
                result.reason })
                + "\n" + string.Join(",", result.changed_paths);
        }

        private static void WriteHeartbeat()
        {
            AtomicJson(Path.Combine(BridgeRoot, "heartbeat.json"), new Heartbeat
            {
                project_root = ProjectRoot,
                editor_version = Application.unityVersion,
                editor_path = EditorApplication.applicationPath,
                process_id = System.Diagnostics.Process.GetCurrentProcess().Id,
                instance_id = InstanceId,
                safe_mode = EditorUtility.scriptCompilationFailed,
                updated_at = DateTime.UtcNow.ToString("o"),
            });
        }

        private static void BeginNext()
        {
            var jobs = Path.Combine(BridgeRoot, "jobs");
            if (!Directory.Exists(jobs)) return;
            foreach (var path in Directory.GetFiles(jobs, "*.json").OrderBy(value => value, StringComparer.Ordinal))
            {
                Ticket ticket;
                try
                {
                    ticket = JsonUtility.FromJson<Ticket>(File.ReadAllText(path));
                    if (ticket == null || !SafeId(ticket.run_id))
                        throw new InvalidDataException("E2E job has no safe run identity");
                }
                catch (Exception exception)
                {
                    // 破損したBridge jobは隔離し、後続の正当なJobを停止させない。
                    var rejected = Path.Combine(BridgeRoot, "rejected");
                    Directory.CreateDirectory(rejected);
                    File.Move(path, Path.Combine(rejected, Path.GetFileName(path) + "." + Guid.NewGuid().ToString("N")));
                    Debug.LogError("UnityAgent rejected a malformed E2E job: " + exception.Message);
                    continue;
                }
                if (!ValidateTicket(ticket))
                {
                    WriteResult(new ActiveJob { ticket = ticket, compile = "not_observed", playmode = "not_observed" },
                        "failed", "E2E ticket signature, Editor binding or deadline is invalid");
                    File.Delete(path);
                    continue;
                }
                var active = new ActiveJob
                {
                    ticket = ticket,
                    phase = "create",
                    compile = "not_observed",
                    playmode = "not_observed",
                    previous_scene_path = SceneManager.GetActiveScene().path,
                };
                Save(active);
                Advance(active);
                return;
            }
        }

        private static bool SafeId(string value)
        {
            return !string.IsNullOrEmpty(value) && value.Length <= 128 && value.All(character =>
                char.IsLetterOrDigit(character) || character == '-' || character == '_' || character == '.');
        }

        private static bool ValidateTicket(Ticket ticket)
        {
            if (!ValidTicketIdentity(ticket) || EditorUtility.scriptCompilationFailed) return false;
            return DateTime.TryParse(ticket.expires_at, null, System.Globalization.DateTimeStyles.RoundtripKind, out var expiry)
                && expiry.ToUniversalTime() > DateTime.UtcNow && ApprovalsActive(ticket);
        }

        private static bool ValidTicketIdentity(Ticket ticket)
        {
            if (ticket == null || ticket.schema_version != "1.0" || !SafeId(ticket.run_id) || !SafeId(ticket.plan_id) ||
                !SafeId(ticket.approval_ref) || !SafeId(ticket.save_approval_ref) ||
                !SameProject(ticket.project_root, ProjectRoot) || ticket.instance_id != InstanceId ||
                string.IsNullOrEmpty(ticket.state_root) || string.IsNullOrEmpty(ticket.plan_digest) ||
                !DateTime.TryParse(ticket.expires_at, null, System.Globalization.DateTimeStyles.RoundtripKind, out _))
                return false;
            var template = AssetDatabase.LoadAssetAtPath<TextAsset>(TemplatePath);
            return template != null && ticket.script_sha256 == "sha256:" + Sha256(template.bytes)
                && Matches(Hmac(JobMessage(ticket)), ticket.signature);
        }

        private static bool ApprovalsActive(Ticket ticket)
        {
            return ApprovalActive(ticket, ticket.approval_ref, ticket.mutation_decision_digest, "editor_mutation",
                ExpectedPaths) && ApprovalActive(ticket, ticket.save_approval_ref, ticket.save_decision_digest, "save",
                    new[] { ScenePath, ScenePath + ".meta" });
        }

        private static bool ApprovalActive(Ticket ticket, string reference, string digest, string kind, string[] paths)
        {
            var recordPath = Path.Combine(ticket.state_root, "approvals", "decisions", reference + ".json");
            if (!File.Exists(recordPath)) return false;
            var record = JsonUtility.FromJson<ApprovalRecord>(File.ReadAllText(recordPath));
            var decision = record == null ? null : record.decision;
            if (record == null || record.schema_version != "1.1" || decision == null ||
                decision.approval_decision_id != reference || decision.approval_kind != kind ||
                decision.plan_id != ticket.plan_id || decision.plan_digest != ticket.plan_digest ||
                decision.decision_digest != digest || decision.status != "active" ||
                decision.human_review != "approved" || decision.revocation_epoch != record.current_revocation_epoch ||
                !SameProject(decision.project_root, ProjectRoot) ||
                decision.scope_paths == null || !decision.scope_paths.SequenceEqual(paths) ||
                !DateTime.TryParse(decision.expires_at, null, System.Globalization.DateTimeStyles.RoundtripKind, out var expiry))
                return false;
            return expiry.ToUniversalTime() > DateTime.UtcNow;
        }

        private static void RequireApprovals(Ticket ticket)
        {
            if (!ApprovalsActive(ticket))
                throw new InvalidOperationException("E2E mutation or save approval is revoked or expired");
        }

        private static string Sha256(byte[] bytes)
        {
            using (var hash = SHA256.Create())
            {
                return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
            }
        }

        private static bool SameProject(string left, string right)
        {
            if (string.IsNullOrEmpty(left) || string.IsNullOrEmpty(right)) return false;
            var comparison = Path.DirectorySeparatorChar == '\\' ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
            return string.Equals(Path.GetFullPath(left).TrimEnd('/', '\\'), Path.GetFullPath(right).TrimEnd('/', '\\'), comparison);
        }

        private static void Advance(ActiveJob active)
        {
            if (active == null || active.ticket == null) throw new InvalidDataException("Active E2E job is corrupt");
            if (DateTime.Parse(active.ticket.expires_at).ToUniversalTime() <= DateTime.UtcNow ||
                !ApprovalsActive(active.ticket))
            {
                active.failure_reason = "E2E approval deadline expired or approval was revoked";
                active.phase = "exit";
                Save(active);
            }
            switch (active.phase)
            {
                case "create": CreateAssets(active); break;
                case "compile": ObserveCompile(active); break;
                case "play": ObservePlaymode(active); break;
                case "exit":
                    if (EditorApplication.isPlaying)
                    {
                        EditorApplication.ExitPlaymode();
                    }
                    else if (!EditorApplication.isPlayingOrWillChangePlaymode)
                    {
                        Finish(active);
                    }
                    break;
                default: throw new InvalidDataException("Unknown E2E job phase");
            }
        }

        private static void CreateAssets(ActiveJob active)
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling || EditorApplication.isUpdating ||
                SceneManager.sceneCount != 1 || SceneManager.GetActiveScene().isDirty)
                throw new InvalidOperationException("Editor must have one saved Scene and be idle before E2E creation");
            if (Directory.Exists(Path.Combine(ProjectRoot, AssetDirectory)) ||
                File.Exists(Path.Combine(ProjectRoot, AssetDirectory + ".meta")))
                throw new InvalidOperationException("E2E target already exists; overwrite is forbidden");
            var template = AssetDatabase.LoadAssetAtPath<TextAsset>(TemplatePath);
            if (template == null || active.ticket.script_sha256 != "sha256:" + Sha256(template.bytes))
                throw new InvalidOperationException("Reviewed E2E script template has changed");
            var shader = Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Unlit/Color") ?? Shader.Find("Standard");
            if (shader == null) throw new InvalidOperationException("No supported Material shader was found");
            RequireApprovals(active.ticket);
            var folderGuid = AssetDatabase.CreateFolder("Assets", "UnityAgentE2E");
            if (string.IsNullOrEmpty(folderGuid) || AssetDatabase.GUIDToAssetPath(folderGuid) != AssetDirectory)
                throw new InvalidOperationException("Unity did not create the exact scoped asset folder");
            RequireApprovals(active.ticket);
            RequireAbsent(MaterialPath);
            var material = new Material(shader) { name = "FullE2EMaterial" };
            AssetDatabase.CreateAsset(material, MaterialPath);
            RequireApprovals(active.ticket);
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
            cube.name = ObjectName;
            cube.GetComponent<Renderer>().sharedMaterial = material;
            RequireApprovals(active.ticket);
            RequireAbsent(ScenePath);
            if (!EditorSceneManager.SaveScene(scene, ScenePath))
                throw new InvalidOperationException("Unity could not save the generated Scene");
            // C# importによるDomain reload前に進行状態を保存する。
            active.phase = "compile";
            active.import_started_at = DateTime.UtcNow.ToString("o");
            Save(active);
            RequireApprovals(active.ticket);
            RequireAbsent(ScriptPath);
            using (var stream = new FileStream(Path.Combine(ProjectRoot, ScriptPath), FileMode.CreateNew, FileAccess.Write))
                stream.Write(template.bytes, 0, template.bytes.Length);
            AssetDatabase.ImportAsset(ScriptPath, ImportAssetOptions.ForceUpdate);
        }

        private static void RequireAbsent(string assetPath)
        {
            if (File.Exists(Path.Combine(ProjectRoot, assetPath)) || File.Exists(Path.Combine(ProjectRoot, assetPath + ".meta")))
                throw new InvalidOperationException("E2E create-only target already exists: " + assetPath);
        }

        private static Type ProbeType()
        {
            var script = AssetDatabase.LoadAssetAtPath<MonoScript>(ScriptPath);
            var type = script == null ? null : script.GetClass();
            return type != null && type.FullName == "DarumaPPAP.UnityAgent.E2E.FullE2EProbe" &&
                   typeof(MonoBehaviour).IsAssignableFrom(type) ? type : null;
        }

        private static void ObserveCompile(ActiveJob active)
        {
            if (EditorApplication.isCompiling || EditorApplication.isUpdating) return;
            if (EditorUtility.scriptCompilationFailed)
                throw new InvalidOperationException("Unity reported script compilation errors");
            var probeType = ProbeType();
            if (probeType == null)
            {
                if (DateTime.TryParse(active.import_started_at, out var imported) &&
                    DateTime.UtcNow - imported.ToUniversalTime() < TimeSpan.FromSeconds(20)) return;
                throw new InvalidOperationException("Generated E2E script did not compile or load");
            }
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            var cube = GameObject.Find(ObjectName);
            var material = AssetDatabase.LoadAssetAtPath<Material>(MaterialPath);
            if (cube == null || material == null || cube.GetComponent<Renderer>() == null ||
                cube.GetComponent<Renderer>().sharedMaterial != material)
                throw new InvalidOperationException("Generated GameObject or its Material is missing from the saved Scene");
            if (cube.GetComponent(probeType) == null) cube.AddComponent(probeType);
            RequireApprovals(active.ticket);
            if (!EditorSceneManager.SaveScene(scene, ScenePath))
                throw new InvalidOperationException("Unity could not save the compiled component in the Scene");
            active.compile = "passed";
            active.phase = "play";
            Save(active);
            EditorApplication.EnterPlaymode();
        }

        private static void ObservePlaymode(ActiveJob active)
        {
            if (!EditorApplication.isPlaying) return;
            var cube = GameObject.Find(ObjectName);
            var type = ProbeType();
            if (cube == null || type == null) return;
            var component = cube.GetComponent(type);
            var property = type.GetProperty("WasStarted");
            if (component == null || property == null || !Equals(property.GetValue(component), true)) return;
            active.playmode = "passed";
            active.phase = "exit";
            Save(active);
            EditorApplication.ExitPlaymode();
        }

        private static void Finish(ActiveJob active)
        {
            var complete = string.IsNullOrEmpty(active.failure_reason) && active.compile == "passed" && active.playmode == "passed";
            if (complete && !ActualPaths().SequenceEqual(ExpectedPaths.OrderBy(path => path, StringComparer.Ordinal)))
            {
                complete = false;
                active.failure_reason = "Editor asset inventory differs from the approved create-only diff";
            }
            if (!string.IsNullOrEmpty(active.previous_scene_path) && File.Exists(Path.Combine(ProjectRoot, active.previous_scene_path)))
            {
                try { EditorSceneManager.OpenScene(active.previous_scene_path, OpenSceneMode.Single); }
                catch (Exception exception)
                {
                    complete = false;
                    active.failure_reason = "UnityAgent could not restore the previous Scene: " + exception.Message;
                    Debug.LogError(active.failure_reason);
                }
            }
            WriteResult(active, complete ? "passed" : "failed", active.failure_reason);
            var jobPath = Path.Combine(BridgeRoot, "jobs", active.ticket.run_id + ".json");
            if (File.Exists(jobPath)) File.Delete(jobPath);
            File.Delete(ActivePath);
        }

        private static string[] ActualPaths()
        {
            var paths = new System.Collections.Generic.List<string>();
            var rootMeta = Path.Combine(ProjectRoot, AssetDirectory + ".meta");
            if (File.Exists(rootMeta)) paths.Add(AssetDirectory + ".meta");
            var directory = Path.Combine(ProjectRoot, AssetDirectory);
            if (Directory.Exists(directory))
            {
                foreach (var path in Directory.GetFiles(directory, "*", SearchOption.AllDirectories))
                    paths.Add(Path.GetRelativePath(ProjectRoot, path).Replace('\\', '/'));
            }
            return paths.OrderBy(path => path, StringComparer.Ordinal).ToArray();
        }

        private static void WriteResult(ActiveJob active, string status, string reason)
        {
            var ticket = active.ticket;
            var result = new EditorResult
            {
                run_id = ticket.run_id,
                project_root = ProjectRoot,
                plan_id = ticket.plan_id,
                approval_ref = ticket.approval_ref,
                save_approval_ref = ticket.save_approval_ref,
                status = status,
                compile = active.compile,
                playmode = active.playmode,
                script_sha256 = ticket.script_sha256,
                instance_id = InstanceId,
                shader_name = AssetDatabase.LoadAssetAtPath<Material>(MaterialPath)?.shader?.name ?? "",
                changed_paths = ActualPaths(),
                reason = reason,
            };
            result.signature = Hmac(ResultMessage(result));
            AtomicJson(Path.Combine(BridgeRoot, "results", ticket.run_id + ".json"), result);
        }

        private static void Save(ActiveJob active)
        {
            AtomicJson(ActivePath, active);
        }

        private static void AtomicJson(string path, object value)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.WriteAllText(temporary, JsonUtility.ToJson(value), new UTF8Encoding(false));
                if (File.Exists(path)) File.Replace(temporary, path, null);
                else File.Move(temporary, path);
            }
            finally
            {
                if (File.Exists(temporary)) File.Delete(temporary);
            }
        }
    }
}
