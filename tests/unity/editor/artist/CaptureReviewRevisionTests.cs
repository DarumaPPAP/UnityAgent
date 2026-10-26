#if UNITY_EDITOR && !ARTIST_AUTHORITY_STANDALONE
using System;
using System.Collections;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using NUnit.Framework;
using UnityEngine;

namespace UnityArtist.Tests
{
	public sealed class CaptureReviewRevisionTests
	{
		[Test]
		public void AuthorizationUsesCaptureRevisionAfterSceneChanges()
		{
			string root = Directory.GetParent(Application.dataPath).FullName;
			string descriptor = Path.Combine(root, "Library/UnityAgent/ArtistAuthority.json");
			if (File.Exists(descriptor))
			{
				Assert.Ignore("実行中のControl Planeのdescriptorを変更しません。");
			}
			Type session = typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
			if ((bool)session.GetField("persistentBatchSession", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null))
			{
				Assert.Ignore("実行中の永続Batch状態へテストのCaptureを保存しません。");
			}
			IDictionary captures = (IDictionary)session.GetField("captures", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
			string captureId = "owned-capture-" + Guid.NewGuid().ToString("N");
			string sessionId = Guid.NewGuid().ToString("N");
			byte[] secret = new byte[32];
			TcpListener listener = new TcpListener(IPAddress.Loopback, 0);
			listener.Start();
			int port = ((IPEndPoint)listener.LocalEndpoint).Port;
			string body = null;
			Task server = Task.Run(() =>
			{
				using (TcpClient client = listener.AcceptTcpClient())
				using (NetworkStream stream = client.GetStream())
				using (StreamReader reader = new StreamReader(stream, Encoding.UTF8, false, 1024, true))
				{
					int size = 0;
					string line;
					while (!string.IsNullOrEmpty(line = reader.ReadLine()))
					{
						if (line.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase))
						{
							size = int.Parse(line.Substring("Content-Length:".Length).Trim());
						}
					}
					char[] chars = new char[size];
					int offset = 0;
					while (offset < size)
					{
						int read = reader.Read(chars, offset, size - offset);
						if (read == 0)
						{
							throw new EndOfStreamException("Incomplete authorization request");
						}
						offset += read;
					}
					body = new string(chars);
					string nonce = Regex.Match(body, "\"nonce\":\"([^\"]+)\"").Groups[1].Value;
					byte[] response = Encoding.UTF8.GetBytes("{\"allowed\":false,\"nonce\":\"" + nonce + "\",\"sessionId\":\"" + sessionId + "\",\"reason\":\"test denies review\",\"reservationId\":\"\"}");
					byte[] message = Encoding.UTF8.GetBytes("response\n" + Encoding.UTF8.GetString(response));
					string signature;
					using (HMACSHA256 hmac = new HMACSHA256(secret)) signature = BitConverter.ToString(hmac.ComputeHash(message)).Replace("-", "").ToLowerInvariant();
					byte[] header = Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + response.Length + "\r\nX-UnityAgent-Signature: " + signature + "\r\nConnection: close\r\n\r\n");
					stream.Write(header, 0, header.Length);
					stream.Write(response, 0, response.Length);
				}
			});
			try
			{
				using SceneFixture fixture = new SceneFixture();
				string capturedRevision = ((ArtistResult)session.GetMethod("Inspect", BindingFlags.Public | BindingFlags.Static).Invoke(null, Array.Empty<object>())).revision;
				RenderSettings.fogDensity += 0.01f;
				Directory.CreateDirectory(Path.GetDirectoryName(descriptor));
				string json = "{\"schemaVersion\":\"1\",\"projectRoot\":\"" + root.Replace("\\", "\\\\") + "\",\"endpoint\":\"http://127.0.0.1:" + port + "/authorize\",\"sessionId\":\"" + sessionId + "\",\"secret\":\"" + new string('0', 64) + "\"}";
				using (FileStream file = new FileStream(descriptor, FileMode.CreateNew, FileAccess.Write))
				{
					byte[] bytes = Encoding.UTF8.GetBytes(json);
					file.Write(bytes, 0, bytes.Length);
				}
				captures.Add(captureId, new ArtistResult { captureId = captureId, revision = capturedRevision, baseRevision = capturedRevision });
				ArtistResult result = (ArtistResult)session.GetMethod("EvaluateAuthenticated", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, new object[] { captureId, "needs_refine", "synthetic review", new string('b', 64), null });
				Assert.That(server.Wait(5000), Is.True);
				Assert.That(body, Does.Contain("\"expectedRevision\":\"" + capturedRevision + "\""));
				Assert.That(result.status, Is.EqualTo("blocked"), "このUnit Testは承認を発行せず、wireのCapture束縛だけを検証します。");
				Assert.That(result.humanReview, Is.False);
			}
			finally
			{
				listener.Stop();
				captures.Remove(captureId);
				if (File.Exists(descriptor) && File.ReadAllText(descriptor).Contains(sessionId))
				{
					File.Delete(descriptor);
				}
			}
		}
	}
}
#endif
