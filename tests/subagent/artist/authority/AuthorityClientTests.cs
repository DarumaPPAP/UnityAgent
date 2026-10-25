#if ARTIST_AUTHORITY_STANDALONE
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using UnityArtist;

internal static class AuthorityClientTests
{
    private static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--live")
        {
            using JsonDocument payload = JsonDocument.Parse(File.ReadAllText(args[1]));
            JsonElement json = payload.RootElement;
            ArtistResult result = new ArtistResult();
            var changes = JsonSerializer.Deserialize<List<ArtistChange>>(json.GetProperty("exactDiff").GetRawText(), new JsonSerializerOptions { IncludeFields = true });
            AuthorityClient.Review review = json.TryGetProperty("review", out JsonElement reviewJson) ? JsonSerializer.Deserialize<AuthorityClient.Review>(reviewJson.GetRawText(), new JsonSerializerOptions { IncludeFields = true }) : null;
            bool allowed = new AuthorityClient().Authorize(json.GetProperty("projectRoot").GetString(), json.GetProperty("command").GetString(), json.GetProperty("planId").GetString(), json.GetProperty("expectedRevision").GetString(), json.GetProperty("approvalToken").GetString(), changes, result, review);
            Console.WriteLine(JsonSerializer.Serialize(new { allowed, result.authoritySessionId, result.authorityNonce, result.authorityReservationId, result.errors }, new JsonSerializerOptions { IncludeFields = true }));
            return allowed ? 0 : 2;
        }
        string root = Path.Combine(Path.GetTempPath(), "artist-authority-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(root, "Library", "UnityAgent"));
        try
        {
            Check(!Authorize(root).allowed, "absent descriptor must deny");
            foreach (string mode in new[] { "allow", "deny", "bad-signature", "bad-nonce", "bad-session", "empty-reservation" }) RunServerCase(root, mode);
            RunServerCase(root, "context");
            foreach (string endpoint in new[] { "http://example.com:1234/authorize", "https://127.0.0.1:1234/authorize", "http://127.0.0.1:1234/other", "http://127.0.0.1:1234/authorize?extra=1", "http://user@127.0.0.1:1234/authorize" })
            {
                File.WriteAllText(Path.Combine(root, "Library", "UnityAgent", "ArtistAuthority.json"), JsonSerializer.Serialize(new { schemaVersion = "1", projectRoot = root, endpoint, sessionId = "abcd", secret = new string('a', 64) }));
                Check(!Authorize(root).allowed, "noncanonical endpoint must deny: " + endpoint);
            }
            foreach (string field in new[] { "schemaVersion", "projectRoot", "sessionId", "secret" })
            {
                var invalid = new Dictionary<string, string> { ["schemaVersion"] = "1", ["projectRoot"] = root, ["endpoint"] = "http://127.0.0.1:1234/authorize", ["sessionId"] = "abcd", ["secret"] = new string('a', 64) };
                invalid[field] = "wrong";
                File.WriteAllText(Path.Combine(root, "Library", "UnityAgent", "ArtistAuthority.json"), JsonSerializer.Serialize(invalid));
                Check(!Authorize(root).allowed, "invalid descriptor must deny: " + field);
            }
            Console.WriteLine("PASS: absent/invalid descriptor, authenticated request/response, deny, signature, nonce, session, reservation");
            return 0;
        }
        catch (Exception exception) { Console.Error.WriteLine(exception); return 1; }
        finally { Directory.Delete(root, true); }
    }

    private static (bool allowed, ArtistResult result) Authorize(string root, bool contextBound = false)
    {
        ArtistResult result = new ArtistResult();
        var values = new Dictionary<string, object> { ["projectRoot"] = root, ["command"] = "artist.apply", ["planId"] = "plan-1", ["expectedRevision"] = "revision-1", ["approvalToken"] = "opaque-token", ["exactDiff"] = new List<ArtistChange> { new ArtistChange { target = "カメラ", property = "fieldOfView", before = "40", after = "45" } }, ["result"] = result, ["mutationPaths"] = contextBound ? new List<string> { "Assets/Owned.unity" } : null, ["context"] = contextBound ? new ContextReceipt { receivedContextId = "context-1", receivedContextFingerprint = "fingerprint-1", projectRoot = root, runId = "run-1" } : null };
        var method = typeof(AuthorityClient).GetMethod("Authorize", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        bool allowed = (bool)method.Invoke(new AuthorityClient(), method.GetParameters().Select(parameter => values.TryGetValue(parameter.Name, out object value) ? value : parameter.DefaultValue).ToArray());
        return (allowed, result);
    }

    private static void RunServerCase(string root, string mode)
    {
        using TcpListener server = new TcpListener(IPAddress.Loopback, 0);
        server.Start();
        int port = ((IPEndPoint)server.LocalEndpoint).Port;
        string secret = new string('a', 64);
        string descriptor = JsonSerializer.Serialize(new { schemaVersion = "1", projectRoot = root, endpoint = "http://127.0.0.1:" + port + "/authorize", sessionId = "abcd", secret });
        File.WriteAllText(Path.Combine(root, "Library", "UnityAgent", "ArtistAuthority.json"), descriptor);
        Task served = Task.Run(() =>
        {
            using TcpClient client = server.AcceptTcpClient();
            using NetworkStream stream = client.GetStream();
            var headerBytes = new List<byte>();
            while (true)
            {
                int value = stream.ReadByte();
                if (value < 0) throw new Exception("request interrupted");
                headerBytes.Add((byte)value);
                if (headerBytes.Count >= 4 && Encoding.ASCII.GetString(headerBytes.ToArray()).EndsWith("\r\n\r\n", StringComparison.Ordinal)) break;
            }
            string headers = Encoding.ASCII.GetString(headerBytes.ToArray());
            int length = 0;
            string signature = null;
            foreach (string line in headers.Split("\r\n"))
            {
                if (line.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase)) length = int.Parse(line.Substring(15).Trim());
                if (line.StartsWith("X-UnityAgent-Signature:", StringComparison.OrdinalIgnoreCase)) signature = line.Substring(23).Trim();
            }
            byte[] body = new byte[length];
            stream.ReadExactly(body);
            Check(signature == Sign(secret, "request\n", body), "request HMAC must bind raw UTF8 bytes");
            using JsonDocument request = JsonDocument.Parse(body);
            JsonElement json = request.RootElement;
            Check(json.GetProperty("projectRoot").GetString() == root && json.GetProperty("planId").GetString() == "plan-1" && json.GetProperty("approvalToken").GetString() == "opaque-token", "request binding");
            Check(json.GetProperty("exactDiff")[0].GetProperty("after").GetString() == "45", "exactDiff binding");
            if (mode == "context")
            {
                Check(json.TryGetProperty("mutationPaths", out JsonElement paths) && paths[0].GetString() == "Assets/Owned.unity", "mutation requires observed Scene/Asset paths before execution");
                Check(json.TryGetProperty("context", out JsonElement context) && context.GetProperty("contextId").GetString() == "context-1" && context.GetProperty("contextFingerprint").GetString() == "fingerprint-1" && context.GetProperty("runId").GetString() == "run-1" && context.GetProperty("projectRoot").GetString() == root, "authorization must bind the actual Pipeline Context before mutation");
            }
            byte[] response = JsonSerializer.SerializeToUtf8Bytes(new { allowed = mode != "deny", nonce = mode == "bad-nonce" ? "wrong" : json.GetProperty("nonce").GetString(), sessionId = mode == "bad-session" ? "wrong" : "abcd", reason = "bounded test", reservationId = mode == "empty-reservation" ? "" : "reservation-1" });
            string responseSignature = mode == "bad-signature" ? new string('0', 64) : Sign(secret, "response\n", response);
            byte[] responseHeaders = Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + response.Length + "\r\nX-UnityAgent-Signature: " + responseSignature + "\r\nConnection: close\r\n\r\n");
            stream.Write(responseHeaders);
            stream.Write(response);
        });
        var outcome = Authorize(root, mode == "context");
        Check(served.Wait(TimeSpan.FromSeconds(5)), "server completion");
        Check(outcome.allowed == (mode == "allow" || mode == "context"), mode + " authorization result");
        if (mode == "allow" || mode == "context") Check(outcome.result.authorityReservationId == "reservation-1", "receipt propagation");
        else Check(outcome.result.errors.Count == 1, "denial must explain failure");
    }

    private static string Sign(string secret, string prefix, byte[] body)
    {
        using HMACSHA256 hmac = new HMACSHA256(Convert.FromHexString(secret));
        return Convert.ToHexString(hmac.ComputeHash(Encoding.UTF8.GetBytes(prefix + Encoding.UTF8.GetString(body)))).ToLowerInvariant();
    }

    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
}

namespace UnityEngine
{
    internal enum RuntimePlatform { WindowsEditor, LinuxEditor }
    internal static class Application { public static RuntimePlatform platform = OperatingSystem.IsWindows() ? RuntimePlatform.WindowsEditor : RuntimePlatform.LinuxEditor; }
    internal static class JsonUtility
    {
        public static string ToJson(object value) => JsonSerializer.Serialize(value, new JsonSerializerOptions { IncludeFields = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
        public static T FromJson<T>(string value) => JsonSerializer.Deserialize<T>(value, new JsonSerializerOptions { IncludeFields = true });
    }
}
namespace UnityArtist
{
    internal sealed class ContextReceipt { public string receivedContextId; public string receivedContextFingerprint; public string projectRoot; public string runId; }
    internal sealed class ArtistChange { public string target; public string property; public string before; public string after; }
    internal sealed class ArtistError { public string code; public string message; }
    internal sealed class ArtistResult
    {
        public string authoritySessionId;
        public string authorityNonce;
        public string authorityReservationId;
        public List<ArtistError> errors = new List<ArtistError>();
    }
}

#endif
