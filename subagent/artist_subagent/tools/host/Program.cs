using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace UnityArtist.Cli;

internal static class Program
{
    public static int Main(string[] args)
    {
        try
        {
            var parsed = CliArguments.Parse(args);
            var result = ArtistCli.Execute(parsed);
            Output.Write(result, parsed.Format);
            return result.ExitCode;
        }
        catch (CliUsageException ex)
        {
            var result = ArtistResult.Blocked("usage", ex.Code, ex.Message);
            Output.Write(result, "json");
            return result.ExitCode;
        }
        catch (Exception ex)
        {
            var result = ArtistResult.Failed("unknown", "UNHANDLED_CLI_FAILURE", ex.Message);
            Output.Write(result, "json");
            return result.ExitCode;
        }
    }
}

internal sealed class CliArguments
{
    private static readonly HashSet<string> BooleanOptions = new(StringComparer.Ordinal)
    {
        "--help", "--non-interactive", "--verbose", "--no-banner"
    };

    private readonly Dictionary<string, string?> _options = new(StringComparer.Ordinal);

    public string Command { get; private set; } = "help";
    public string Format => Get("--format") ?? "human";
    public IReadOnlyDictionary<string, string?> Options => _options;

    public string? Get(string name) => _options.TryGetValue(name, out var value) ? value : null;

    public bool Has(string name) => _options.ContainsKey(name);

    public static CliArguments Parse(IReadOnlyList<string> args)
    {
        var parsed = new CliArguments();
        var index = 0;
        if (args.Count > 0 && !args[0].StartsWith("-", StringComparison.Ordinal))
        {
            parsed.Command = args[0].ToLowerInvariant();
            index = 1;
        }

        while (index < args.Count)
        {
            var token = args[index++];
            if (!token.StartsWith("--", StringComparison.Ordinal))
            {
                throw new CliUsageException("POSITIONAL_ARGUMENT", $"Unexpected argument: {token}");
            }

            if (BooleanOptions.Contains(token))
            {
                parsed._options[token] = "true";
                continue;
            }

            if (index >= args.Count || args[index].StartsWith("--", StringComparison.Ordinal))
            {
                throw new CliUsageException("MISSING_OPTION_VALUE", $"Option requires a value: {token}");
            }
            parsed._options[token] = args[index++];
        }

        if (!new[] { "human", "json", "ndjson" }.Contains(parsed.Format, StringComparer.OrdinalIgnoreCase))
        {
            throw new CliUsageException("INVALID_FORMAT", "--format must be human, json, or ndjson.");
        }
        return parsed;
    }
}

internal static class ArtistCli
{
    private const string Product = "UnityArtistCLI";
    private const string Version = "0.0.2-beta";
    private const string SemanticVersion = "0.0.2-beta";
    private const string PackageId = "com.darumappap.artist-subagent";
    private const string UnityCommand = "unity";
    private static readonly HashSet<string> SupportedCommands = new(StringComparer.Ordinal)
    {
        "help", "version", "doctor", "capabilities", "install", "inspect", "plan", "preview", "apply", "capture", "evaluate", "refine", "cinematic", "history"
    };

    public static ArtistResult Execute(CliArguments args)
    {
        if (!SupportedCommands.Contains(args.Command))
        {
            return ArtistResult.Blocked("usage", "UNKNOWN_COMMAND", $"Unknown UnityArtistCLI command: {args.Command}");
        }

        return args.Command switch
        {
            "help" => Help(),
            "version" => VersionInfo(),
            "capabilities" => Capabilities(args),
            "doctor" => Doctor(args),
            "install" => Install(args),
            "inspect" or "plan" or "preview" or "apply" or "capture" or "evaluate" or "refine" or "cinematic" or "history" =>
                ExecuteArtistCommand(args),
            _ => ArtistResult.Blocked("usage", "UNKNOWN_COMMAND", args.Command)
        };
    }

    private static ArtistResult Help() => ArtistResult.Passed("help", new
    {
        product = Product,
        executable = "unity-artist",
        usage = "unity artist <command> --project-path <path> --format json --non-interactive",
        commands = SupportedCommands.OrderBy(value => value).ToArray(),
        transport = "official_unity_cli_pipeline",
        artistOnlySurface = new[]
        {
            "lookdev.inspect", "lookdev.plan", "lighting.plan", "environment.plan", "camera.plan",
            "cinematic.timeline", "capture.visual", "evaluate.visual", "refine.visual"
        },
        delegatedToOfficialUnityCli = new[]
        {
            "project.open", "project.test", "project.build", "editor.status", "pipeline.install", "command.discovery"
        },
        safety = "inspect -> exact plan/diff -> expected revision -> external approval -> apply -> evidence",
        forbidden = new[] { "generic GameObject CRUD", "arbitrary eval", "automatic save", "silent fallback" }
    });

    private static ArtistResult VersionInfo() => ArtistResult.Passed("version", new
    {
        product = Product,
        version = Version,
        semanticVersion = SemanticVersion,
        packageId = PackageId,
        executable = "unity-artist",
        transport = "official_unity_cli_pipeline",
        compatibilityBackend = "builtin_editor_api_or_native_srp_adapter"
    });

    private static ArtistResult Capabilities(CliArguments args)
    {
        var data = new Dictionary<string, object?>
        {
            ["product"] = Product,
            ["version"] = Version,
            ["semanticVersion"] = SemanticVersion,
            ["commands"] = SupportedCommands.OrderBy(value => value).ToArray(),
            ["transport"] = "official_unity_cli_pipeline",
            ["capabilities"] = new[]
            {
                "visual_art.inspect", "visual_art.lookdev_plan", "visual_art.lighting_plan",
                "visual_art.environment_plan", "visual_art.camera_plan", "visual_art.capture",
                "visual_art.evaluate", "visual_art.refine", "cinematic.timeline_plan",
                "cinematic.shot_plan", "cinematic.binding_plan"
            },
            ["releaseMatrix"] = SupportMatrix.ReleaseMatrix
        };
        var project = args.Get("--project-path");
        if (!string.IsNullOrWhiteSpace(project))
        {
            var facts = ProjectFacts.Read(project!);
            data["project"] = facts;
            data["support"] = SupportMatrix.Resolve(facts);
        }
        return ArtistResult.Passed("capabilities", data);
    }

    private static ArtistResult Doctor(CliArguments args)
    {
        var unityPath = UnityCliTransport.ResolveExecutable();
        var checks = new Dictionary<string, object?>
        {
            ["officialUnityCli"] = new { available = unityPath is not null, executablePath = unityPath },
            ["packageId"] = PackageId,
            ["transport"] = "official_unity_cli_pipeline",
            ["pipelinePackage"] = "observed_from_project_manifest",
            ["timeline"] = "observed_from_project_manifest",
            ["cinemachine"] = "observed_from_project_manifest",
            ["safeMode"] = "observed_by_unity_pipeline",
            ["approval"] = "owned_by_UnityAgent",
            ["arbitraryEval"] = "not_used"
        };
        var errors = new List<ArtistError>();
        if (unityPath is null)
        {
            errors.Add(new ArtistError("UNITY_CLI_UNAVAILABLE", "Official Unity CLI was not found on PATH."));
        }

        var projectPath = args.Get("--project-path");
        if (string.IsNullOrWhiteSpace(projectPath))
        {
            errors.Add(new ArtistError("PROJECT_PATH_REQUIRED", "doctor requires --project-path to validate the target project."));
        }
        else
        {
            var facts = ProjectFacts.Read(projectPath!);
            checks["project"] = facts;
            checks["support"] = SupportMatrix.Resolve(facts);
            checks["package"] = new
            {
                artist = facts.ArtistPackageInstalled,
                pipeline = facts.PipelinePackageInstalled,
                timeline = facts.TimelinePackageInstalled,
                cinemachine = facts.CinemachinePackageInstalled
            };
            if (!facts.IsUnityProject)
            {
                errors.Add(new ArtistError("PROJECT_NOT_UNITY_PROJECT", "The project must contain Assets, Packages, and ProjectSettings."));
            }
            var support = SupportMatrix.Resolve(facts);
            if (!support.Supported)
            {
                errors.Add(new ArtistError(support.ErrorCode, support.Reason));
            }
        }

        return errors.Count == 0
            ? ArtistResult.Passed("doctor", checks)
            : ArtistResult.Blocked("doctor", errors, checks);
    }

    private static ArtistResult Install(CliArguments args)
    {
        var project = RequireProject(args);
        if (project is null)
        {
            return ArtistResult.Blocked("install", "PROJECT_PATH_REQUIRED", "install requires --project-path.");
        }
        var facts = ProjectFacts.Read(project);
        if (!facts.IsUnityProject)
        {
            return ArtistResult.Blocked("install", "PROJECT_NOT_UNITY_PROJECT", "The target is not a Unity project.");
        }
        var support = SupportMatrix.Resolve(facts);
        if (!support.Supported)
        {
            return ArtistResult.Blocked("install", support.ErrorCode, support.Reason, new { support });
        }
        var cli = UnityCliTransport.ResolveExecutable();
        if (cli is null)
        {
            return ArtistResult.Blocked("install", "UNITY_CLI_UNAVAILABLE", "Official Unity CLI was not found on PATH.");
        }
        var outcome = UnityCliTransport.Run(cli, new[] { "pipeline", "install", "--project-path", project, "--format", "json", "--non-interactive", "--no-banner" }, 120);
        return outcome.ToArtistResult("install", "PIPELINE_INSTALL_FAILED");
    }

    private static ArtistResult ExecuteArtistCommand(CliArguments args)
    {
        var project = RequireProject(args);
        if (project is null)
        {
            return ArtistResult.Blocked(args.Command, "PROJECT_PATH_REQUIRED", $"{args.Command} requires --project-path.");
        }
        var facts = ProjectFacts.Read(project);
        if (!facts.IsUnityProject)
        {
            return ArtistResult.Blocked(args.Command, "PROJECT_NOT_UNITY_PROJECT", "The target is not a Unity project.");
        }
        var support = SupportMatrix.Resolve(facts);
        if (!support.Supported)
        {
            return ArtistResult.Blocked(args.Command, support.ErrorCode, support.Reason, new { support });
        }
        object? contextReceipt = null;
        var contextPath = args.Get("--context-manifest-path");
        if (!string.IsNullOrWhiteSpace(contextPath))
        {
            try
            {
                using var manifest = JsonDocument.Parse(File.ReadAllText(contextPath));
                var view = manifest.RootElement.GetProperty("materialized_context");
                var specialist = view.GetProperty("specialist_context");
                var receivedContextId = view.GetProperty("context_id").GetString();
                var receivedContextFingerprint = view.GetProperty("context_fingerprint").GetProperty("value").GetString();
                if (specialist.ValueKind != JsonValueKind.Object || string.IsNullOrWhiteSpace(receivedContextId) ||
                    string.IsNullOrWhiteSpace(receivedContextFingerprint))
                {
                    return ArtistResult.Blocked(args.Command, "CONTEXT_RECEIPT_INVALID", "Specialist Context identity is incomplete.");
                }
                contextReceipt = new { receivedContextId, receivedContextFingerprint };
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or KeyNotFoundException or InvalidOperationException)
            {
                return ArtistResult.Blocked(args.Command, "CONTEXT_RECEIPT_INVALID", exception.Message);
            }
        }
        var cinematicApply = args.Command == "cinematic" && string.Equals(args.Get("--operation"), "apply", StringComparison.OrdinalIgnoreCase);
        if (args.Command == "apply" || cinematicApply)
        {
            if (string.IsNullOrWhiteSpace(args.Get("--plan-id")))
            {
                return ArtistResult.Blocked(args.Command, "PLAN_ID_REQUIRED", "apply requires --plan-id.");
            }
            if (string.IsNullOrWhiteSpace(args.Get("--approval-token")))
            {
                return ArtistResult.Blocked(args.Command, "APPROVAL_REQUIRED", "apply requires an opaque approval token issued by UnityAgent.");
            }
            if (string.IsNullOrWhiteSpace(args.Get("--expected-revision")))
            {
                return ArtistResult.Blocked(args.Command, "EXPECTED_REVISION_REQUIRED", "apply requires --expected-revision.");
            }
        }

        var mutationRequested = args.Command == "apply" || cinematicApply;
        var timeout = ParseTimeout(args.Get("--timeout"));
        var cli = UnityCliTransport.ResolveExecutable();
        if (cli is null)
        {
            return ArtistResult.Blocked(args.Command, "UNITY_CLI_UNAVAILABLE", "Official Unity CLI was not found on PATH.");
        }

        var pipelineCommand = $"artist.{args.Command}";
        var commandArguments = new List<string> { "command", pipelineCommand, "--project-path", project };
        AddOptional(commandArguments, args, "--request-json", "--request-json");
        AddOptional(commandArguments, args, "--intent-file", "--intent-file");
        AddOptional(commandArguments, args, "--plan-id", "--plan-id");
        AddOptional(commandArguments, args, "--capture-id", "--capture-id");
        AddOptional(commandArguments, args, "--evaluation-id", "--evaluation-id");
        AddOptional(commandArguments, args, "--expected-revision", "--expected-revision");
        AddOptional(commandArguments, args, "--approval-token", "--approval-token");
        AddOptional(commandArguments, args, "--decision", "--decision");
        AddOptional(commandArguments, args, "--notes", "--notes");
        AddOptional(commandArguments, args, "--operation", "--operation");
        commandArguments.Add("--format");
        commandArguments.Add("json");
        commandArguments.Add("--non-interactive");
        commandArguments.Add("--no-banner");

        var outcome = UnityCliTransport.Run(cli, commandArguments, timeout);
        var result = outcome.ToArtistResult(args.Command, "ARTIST_PIPELINE_COMMAND_FAILED", new
        {
            pipelineCommand,
            projectPath = project,
            supportTier = support.SupportTier,
            renderPipeline = support.RenderPipeline,
            unityVersion = support.UnityVersion,
            readOnly = !mutationRequested,
            mutation = mutationRequested ? "approval_and_revision_gated" : "none"
        });
        return result.Status == "passed" && contextReceipt is not null
            ? ArtistResult.Passed(args.Command, new { contextReceipt, backendResult = result.Data })
            : result;
    }

    private static void AddOptional(List<string> destination, CliArguments args, string option, string pipelineOption)
    {
        var value = args.Get(option);
        if (!string.IsNullOrWhiteSpace(value))
        {
            destination.Add(pipelineOption);
            destination.Add(value!);
        }
    }

    private static string? RequireProject(CliArguments args)
    {
        var value = args.Get("--project-path");
        return string.IsNullOrWhiteSpace(value) ? null : Path.GetFullPath(value);
    }

    private static int ParseTimeout(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return 30;
        if (!int.TryParse(value, out var timeout) || timeout < 1 || timeout > 900)
        {
            throw new CliUsageException("INVALID_TIMEOUT", "--timeout must be an integer between 1 and 900 seconds.");
        }
        return timeout;
    }
}

internal sealed record ArtistError(string Code, string Message);

internal sealed class ArtistResult
{
    public string SchemaVersion { get; init; } = "2.0";
    public string Product { get; init; } = "UnityArtistCLI";
    public string Command { get; init; } = "unknown";
    public string Status { get; init; } = "passed";
    public bool Verified { get; init; }
    public int ExitCode { get; init; }
    public object? Data { get; init; }
    public IReadOnlyList<ArtistError> Errors { get; init; } = Array.Empty<ArtistError>();
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();

    public static ArtistResult Passed(string command, object? data) => new()
    {
        Command = command, Status = "passed", Verified = true, ExitCode = 0, Data = data
    };

    public static ArtistResult Blocked(string command, string code, string message, object? data = null) =>
        Blocked(command, new[] { new ArtistError(code, message) }, data);

    public static ArtistResult Blocked(string command, IReadOnlyList<ArtistError> errors, object? data = null) => new()
    {
        Command = command, Status = "blocked", Verified = false, ExitCode = 3, Data = data, Errors = errors
    };

    public static ArtistResult Failed(string command, string code, string message, object? data = null) => new()
    {
        Command = command, Status = "failed", Verified = false, ExitCode = 4, Data = data,
        Errors = new[] { new ArtistError(code, message) }
    };
}

internal static class Output
{
    public static void Write(ArtistResult result, string format)
    {
        var options = new JsonSerializerOptions
        {
            WriteIndented = format.Equals("human", StringComparison.OrdinalIgnoreCase),
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        };
        var json = JsonSerializer.Serialize(result, options);
        if (format.Equals("human", StringComparison.OrdinalIgnoreCase))
        {
            Console.WriteLine($"{result.Product} {result.Command}: {result.Status}");
            if (result.Data is not null) Console.WriteLine(json);
            foreach (var error in result.Errors) Console.Error.WriteLine($"{error.Code}: {error.Message}");
            return;
        }
        if (format.Equals("ndjson", StringComparison.OrdinalIgnoreCase))
        {
            Console.WriteLine(JsonSerializer.Serialize(new { type = "result", result }, options));
            return;
        }
        Console.WriteLine(json);
    }
}

internal sealed class CliUsageException : Exception
{
    public string Code { get; }
    public CliUsageException(string code, string message) : base(message) => Code = code;
}

internal sealed record ProjectFacts(
    string ProjectPath,
    bool IsUnityProject,
    string? UnityVersion,
    string RenderPipeline,
    bool PipelinePackageInstalled,
    bool ArtistPackageInstalled,
    bool TimelinePackageInstalled,
    bool CinemachinePackageInstalled,
    string? ManifestDigest)
{
    public static ProjectFacts Read(string projectPath)
    {
        var root = Path.GetFullPath(projectPath);
        var assets = Directory.Exists(Path.Combine(root, "Assets"));
        var packages = Directory.Exists(Path.Combine(root, "Packages"));
        var settings = Directory.Exists(Path.Combine(root, "ProjectSettings"));
        var versionFile = Path.Combine(root, "ProjectSettings", "ProjectVersion.txt");
        string? unityVersion = null;
        if (File.Exists(versionFile))
        {
            var line = File.ReadLines(versionFile).FirstOrDefault(value => value.StartsWith("m_EditorVersion:", StringComparison.Ordinal));
            unityVersion = line?.Split(':', 2).ElementAtOrDefault(1)?.Trim();
        }

        var manifestPath = Path.Combine(root, "Packages", "manifest.json");
        var manifest = File.Exists(manifestPath) ? File.ReadAllText(manifestPath) : "";
        var renderPipeline = "builtin";
        if (manifest.Contains("render-pipelines.high-definition", StringComparison.OrdinalIgnoreCase)) renderPipeline = "hdrp";
        if (manifest.Contains("render-pipelines.universal", StringComparison.OrdinalIgnoreCase))
        {
            renderPipeline = renderPipeline == "hdrp" ? "unknown" : "urp";
        }
        var digest = manifest.Length == 0 ? null : Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(manifest))).ToLowerInvariant();
        return new ProjectFacts(root, assets && packages && settings, unityVersion, renderPipeline,
            manifest.Contains("com.unity.pipeline", StringComparison.OrdinalIgnoreCase),
            manifest.Contains("com.darumappap.artist-subagent", StringComparison.OrdinalIgnoreCase),
            manifest.Contains("com.unity.timeline", StringComparison.OrdinalIgnoreCase),
            manifest.Contains("com.unity.cinemachine", StringComparison.OrdinalIgnoreCase),
            digest);
    }
}

internal sealed record SupportFacts(
    bool Supported,
    string SupportTier,
    string UnityVersion,
    string RenderPipeline,
    string Transport,
    string CompatibilityBackend,
    string ErrorCode,
    string Reason);

internal sealed class BatchRequest
{
    public string Command { get; init; } = "";
    public string RequestJson { get; init; } = "";
    public string PlanId { get; init; } = "";
    public string CaptureId { get; init; } = "";
    public string EvaluationId { get; init; } = "";
    public string ExpectedRevision { get; init; } = "";
    public string ApprovalToken { get; init; } = "";
    public string Decision { get; init; } = "";
    public string Notes { get; init; } = "";
    public string Operation { get; init; } = "";
    public string ScenePath { get; init; } = "";
}

internal static class SupportMatrix
{
    public static object[] ReleaseMatrix => new object[]
    {
        new { unityVersion = "Unity 6.x+", renderPipeline = "builtin", supportTier = "primary", supported = true, transport = "official_unity_cli_pipeline" },
        new { unityVersion = "Unity 6.x+", renderPipeline = "urp", supportTier = "primary", supported = true, transport = "official_unity_cli_pipeline" },
        new { unityVersion = "Unity 6.x+", renderPipeline = "hdrp", supportTier = "primary", supported = true, transport = "official_unity_cli_pipeline" }
    };

    public static SupportFacts Resolve(ProjectFacts facts)
    {
        var version = facts.UnityVersion ?? "unknown";
        if (!facts.IsUnityProject)
        {
            return Unsupported(version, facts.RenderPipeline, "PROJECT_NOT_UNITY_PROJECT", "Unity project structure is incomplete.");
        }
        if (facts.RenderPipeline == "unknown")
        {
            return Unsupported(version, facts.RenderPipeline, "UNKNOWN_RENDER_PIPELINE", "URP and HDRP package signals conflict; mutation is refused.");
        }
        if (version.StartsWith("6000.", StringComparison.OrdinalIgnoreCase) || version.StartsWith("Unity 6", StringComparison.OrdinalIgnoreCase))
        {
            return Supported(version, facts.RenderPipeline, facts.RenderPipeline == "builtin" ? "builtin_editor_api" : $"{facts.RenderPipeline}_native_api");
        }
        return Unsupported(version, facts.RenderPipeline, "UNSUPPORTED_UNITY_VERSION", "The formal release matrix does not include this Unity version.");
    }

    private static SupportFacts Supported(string version, string pipeline, string backend) =>
        new(true, "primary", version, pipeline, "official_unity_cli_pipeline", backend, "", "");

    private static SupportFacts Unsupported(string version, string pipeline, string code, string reason) =>
        new(false, "unsupported", version, pipeline, "official_unity_cli_pipeline", "none", code, reason);
}

internal sealed record UnityCliOutcome(int ExitCode, bool TimedOut, string Stdout, string Stderr)
{
    public object ToEvidence() => new { exitCode = ExitCode, timedOut = TimedOut, failureClass = "official_cli_failure", stdout = Stdout, stderr = Stderr };

    public ArtistResult ToArtistResult(string command, string failureCode, object? data = null)
    {
        if (TimedOut) return ArtistResult.Blocked(command, "TIMEOUT", "Official Unity CLI exceeded the bounded timeout.", data);
        if (ExitCode != 0)
        {
            var message = string.IsNullOrWhiteSpace(Stderr) ? "Official Unity CLI command failed." : Stderr.Trim();
            var detail = TryParse(Stdout);
            return ArtistResult.Blocked(command, new[] { new ArtistError(failureCode, message) }, data ?? detail);
        }
        var parsed = TryParse(Stdout);
        if (parsed is not null && parsed.Value.TryGetProperty("success", out var success) && success.ValueKind == JsonValueKind.False)
        {
            return ArtistResult.Blocked(command, failureCode, "Official Unity CLI returned a structured failure.", data ?? parsed.Value.Clone());
        }
        return ArtistResult.Passed(command, data is null ? parsed : new { adapter = data, provider = parsed });
    }

    private static JsonElement? TryParse(string value)
    {
        try
        {
            using var document = JsonDocument.Parse(value);
            return document.RootElement.Clone();
        }
        catch (JsonException) { return null; }
    }
}

internal static class UnityCliTransport
{
    public static UnityCliOutcome ProbePipelineInstall(string executable, string project)
    {
        return Run(executable, new[]
        {
            "pipeline", "install", "--project-path", project,
            "--format", "json", "--non-interactive", "--no-banner"
        }, 120);
    }

    public static string? ResolveExecutable()
    {
        var explicitPath = Environment.GetEnvironmentVariable("UNITY_CLI_PATH");
        if (!string.IsNullOrWhiteSpace(explicitPath) && File.Exists(explicitPath)) return explicitPath;
        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var directory in path.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            foreach (var candidate in OperatingSystem.IsWindows() ? new[] { "unity.exe", "unity.cmd", "unity.bat" } : new[] { "unity" })
            {
                var full = Path.Combine(directory.Trim(), candidate);
                if (File.Exists(full)) return full;
            }
        }
        return null;
    }

    public static UnityCliOutcome Run(string executable, IEnumerable<string> arguments, int timeoutSeconds, IReadOnlyDictionary<string, string?>? environment = null)
    {
        using var process = new Process();
        process.StartInfo = new ProcessStartInfo
        {
            FileName = executable,
            WorkingDirectory = Environment.CurrentDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        foreach (var argument in arguments) process.StartInfo.ArgumentList.Add(argument);
        if (environment is not null)
        {
            foreach (var entry in environment)
            {
                process.StartInfo.Environment[entry.Key] = entry.Value ?? string.Empty;
            }
        }
        try
        {
            if (!process.Start()) return new UnityCliOutcome(-1, false, "", "Unable to start official Unity CLI.");
            var stdoutTask = process.StandardOutput.ReadToEndAsync();
            var stderrTask = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit(timeoutSeconds * 1000))
            {
                try { process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
                return new UnityCliOutcome(-1, true, stdoutTask.GetAwaiter().GetResult(), stderrTask.GetAwaiter().GetResult());
            }
            return new UnityCliOutcome(process.ExitCode, false, stdoutTask.GetAwaiter().GetResult(), stderrTask.GetAwaiter().GetResult());
        }
        catch (Exception ex)
        {
            return new UnityCliOutcome(-1, false, "", ex.Message);
        }
    }
}
