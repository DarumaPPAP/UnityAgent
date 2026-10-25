#if UNITY_EDITOR && !ARTIST_AUTHORITY_STANDALONE
using System;
using System.Collections;
using System.IO;
using System.Linq;
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
	public sealed class LookDevVerificationFailureTests
	{
#if UNITY_ARTIST_TEST_FAULTS
		[Test]
		public void ExceptionAfterSuccessfulMutationRollsBackAndRetryRequiresFreshAuthorization()
		{
			Type session = typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
			FieldInfo fault = session.GetField("BeforeLookDevVerificationForTests", BindingFlags.NonPublic | BindingFlags.Static);
			Assert.That(fault, Is.Not.Null, "専用コンパイル記号のあるテストでだけ検証例外を注入します。");
			string root = Directory.GetParent(Application.dataPath).FullName;
			string descriptor = Path.Combine(root, "Library/UnityAgent/ArtistAuthority.json");
			// 他の実行が所有する認証状態や永続Planをテスト用に上書きしない。
			if (File.Exists(descriptor) || (bool)session.GetField("persistentBatchSession", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null))
			{
				Assert.Ignore("Control Planeまたは永続Batchセッションが実行中です。");
			}
			Assert.That(fault.GetValue(null), Is.Null, "別テストの注入状態を上書きしません。");
			using SceneFixture fixture = new SceneFixture();
			Light light = new GameObject("Owned verification light " + Guid.NewGuid().ToString("N")).AddComponent<Light>();
			light.intensity = 1.25f;
			ArtistResult plan = (ArtistResult)session.GetMethod("Plan").Invoke(null, new object[] { JsonUtility.ToJson(new ArtistIntent { targetName = light.name, setLightIntensity = true, lightIntensity = 2.5f }), "" });
			string sessionId = Guid.NewGuid().ToString("N");
			string token = Guid.NewGuid().ToString("N");
			string failure = "owned-post-apply-verification-fault";
			byte[] secret = new byte[32];
			TcpListener listener = new TcpListener(IPAddress.Loopback, 0);
			Task server = null;
			int faultCalls = 0;
			try
			{
				Assert.That(plan.errors, Is.Empty);
				listener.Start();
				int port = ((IPEndPoint)listener.LocalEndpoint).Port;
				Directory.CreateDirectory(Path.GetDirectoryName(descriptor));
				string json = "{\"schemaVersion\":\"1\",\"projectRoot\":\"" + root.Replace("\\", "\\\\") + "\",\"endpoint\":\"http://127.0.0.1:" + port + "/authorize\",\"sessionId\":\"" + sessionId + "\",\"secret\":\"" + new string('0', 64) + "\"}";
				using (FileStream file = new FileStream(descriptor, FileMode.CreateNew, FileAccess.Write))
				{
					byte[] bytes = Encoding.UTF8.GetBytes(json);
					file.Write(bytes, 0, bytes.Length);
				}
				// 外部Authorityの一回限りの認可を再現し、Editor内に承認の代替経路を作らない。
				server = Task.Run(() => ServeOneShotAuthority(listener, sessionId, secret, token, plan.planId));
				fault.SetValue(null, (Action)(() =>
				{
					faultCalls++;
					Assert.That(light.intensity, Is.EqualTo(2.5f), "適用前の例外ではRollbackの回帰を検出できません。");
					throw new InvalidOperationException(failure);
				}));
				ArtistResult result = (ArtistResult)session.GetMethod("Apply").Invoke(null, new object[] { plan.planId, plan.revision, token });
				Assert.That(faultCalls, Is.EqualTo(1));
				Assert.That(result.errors.Any(error => error.code == "MUTATION_FAILED" && error.message == failure), Is.True);
				Assert.That(result.status, Is.EqualTo("blocked"));
				Assert.That(result.verified, Is.False);
				Assert.That(result.exactDiff, Is.Empty);
				Assert.That(result.evidence, Is.Empty, "失敗応答へ成功Evidenceを残してはいけません。");
				Assert.That(result.authorityReservationId, Is.EqualTo("owned-reservation"));
				Assert.That(light.intensity, Is.EqualTo(1.25f), "検証例外でも適用済みの変更をUndoで戻します。");
				Assert.That(((IList)session.GetField("history", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Contains("applied:" + plan.planId), Is.False);
				ArtistResult retried = (ArtistResult)session.GetMethod("Apply").Invoke(null, new object[] { plan.planId, plan.revision, token });
				Assert.That(server.Wait(5000), Is.True);
				Assert.That(retried.status, Is.EqualTo("blocked"));
				Assert.That(retried.errors.Any(error => error.code == "APPROVAL_INVALID"), Is.True);
				Assert.That(retried.authorityReservationId, Is.Null.Or.Empty);
				Assert.That(retried.verified, Is.False);
				Assert.That(retried.evidence, Is.Empty);
				Assert.That(light.intensity, Is.EqualTo(1.25f));
				Assert.That(faultCalls, Is.EqualTo(1), "再認可が拒否された場合は適用後の処理へ進みません。");
			}
			finally
			{
				fault.SetValue(null, null);
				listener.Stop();
				// テストが発行したPlanとdescriptorだけを破棄する。
				if (!string.IsNullOrEmpty(plan.planId))
				{
					((IDictionary)session.GetField("plans", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(plan.planId);
					IList history = (IList)session.GetField("history", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
					history.Remove(plan.planId);
					history.Remove("applied:" + plan.planId);
				}
				if (File.Exists(descriptor) && File.ReadAllText(descriptor).Contains(sessionId))
				{
					File.Delete(descriptor);
				}
			}
		}

		private void ServeOneShotAuthority(TcpListener listener, string sessionId, byte[] secret, string token, string planId)
		{
			for (int requestIndex = 0; requestIndex < 2; requestIndex++)
			{
				using TcpClient client = listener.AcceptTcpClient();
				using NetworkStream stream = client.GetStream();
				stream.ReadTimeout = 5000;
				using StreamReader reader = new StreamReader(stream, Encoding.UTF8, false, 1024, true);
				int size = 0;
				string signature = null;
				string line;
				while (!string.IsNullOrEmpty(line = reader.ReadLine()))
				{
					if (line.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase))
					{
						size = int.Parse(line.Substring("Content-Length:".Length).Trim());
					}
					if (line.StartsWith("X-UnityAgent-Signature:", StringComparison.OrdinalIgnoreCase))
					{
						signature = line.Substring("X-UnityAgent-Signature:".Length).Trim();
					}
				}
				char[] body = new char[size];
				int offset = 0;
				while (offset < size)
				{
					int read = reader.Read(body, offset, size - offset);
					if (read == 0)
					{
						throw new EndOfStreamException("Incomplete owned authorization request");
					}
					offset += read;
				}
				string request = new string(body);
				if (signature != Sign(secret, "request\n" + request) || !request.Contains("\"approvalToken\":\"" + token + "\"") || !request.Contains("\"planId\":\"" + planId + "\""))
				{
					throw new InvalidOperationException("Owned authority request binding failed");
				}
				string nonce = Regex.Match(request, "\"nonce\":\"([^\"]+)\"").Groups[1].Value;
				bool allowed = requestIndex == 0;
				string responseText = "{\"allowed\":" + (allowed ? "true" : "false") + ",\"nonce\":\"" + nonce + "\",\"sessionId\":\"" + sessionId + "\",\"reason\":\"owned one-shot authorization\",\"reservationId\":\"" + (allowed ? "owned-reservation" : "") + "\"}";
				byte[] response = Encoding.UTF8.GetBytes(responseText);
				byte[] header = Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + response.Length + "\r\nX-UnityAgent-Signature: " + Sign(secret, "response\n" + responseText) + "\r\nConnection: close\r\n\r\n");
				stream.Write(header, 0, header.Length);
				stream.Write(response, 0, response.Length);
			}
		}

		private string Sign(byte[] secret, string message)
		{
			using HMACSHA256 hmac = new HMACSHA256(secret);
			return BitConverter.ToString(hmac.ComputeHash(Encoding.UTF8.GetBytes(message))).Replace("-", "").ToLowerInvariant();
		}
#else
		[Test]
		public void NormalCompilationDoesNotExposeVerificationFaultHook()
		{
			Type session = typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
			Assert.That(session.GetField("BeforeLookDevVerificationForTests", BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Static), Is.Null, "通常のEditor assemblyへテスト用例外注入経路を含めません。");
		}
#endif
	}
}
#endif
