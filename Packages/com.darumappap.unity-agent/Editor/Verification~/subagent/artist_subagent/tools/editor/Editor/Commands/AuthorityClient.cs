#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using UnityEngine;

namespace UnityArtist
{
	// Control Plane が呼出し期間だけ所有する descriptor を読み、CLI の直接 Apply でも承認境界を通す。
	// 同一 OS ユーザーによる任意ファイル改竄や任意 C# 実行は、この bounded CLI 境界の対象外。
	internal sealed class AuthorityClient
	{
		[Serializable]
		private sealed class Descriptor
		{
			public string schemaVersion;
			public string projectRoot;
			public string endpoint;
			public string sessionId;
			public string secret;
		}

		[Serializable]
		private class Request
		{
			public string sessionId;
			public string nonce;
			public string projectRoot;
			public string command;
			public string planId;
			public string expectedRevision;
			public string approvalToken;
			public List<ArtistChange> exactDiff;
		}

		[Serializable]
		internal sealed class Review
		{
			public string captureId;
			public string decision;
			public string notes;
		}

		[Serializable]
		private sealed class ReviewRequest : Request
		{
			public Review review;
			public RequestContext context;
		}

		[Serializable]
		private sealed class MutationRequest : Request
		{
			public List<string> mutationPaths;
			public RequestContext context;
		}

		[Serializable]
		private sealed class RequestContext
		{
			public string contextId;
			public string contextFingerprint;
			public string projectRoot;
			public string runId;
		}

		[Serializable]
		private sealed class Response
		{
			public bool allowed;
			public string nonce;
			public string sessionId;
			public string reason;
			public string reservationId;
		}

		internal bool Authorize(string projectRoot, string command, string planId, string expectedRevision, string approvalToken, List<ArtistChange> exactDiff, ArtistResult result, Review review = null, List<string> mutationPaths = null, ContextReceipt context = null)
		{
			string descriptorPath = Path.Combine(projectRoot, "Library", "UnityAgent", "ArtistAuthority.json");
			if (!File.Exists(descriptorPath))
			{
				// 正規の呼出し期間外では Scene の変更を開始しない。
				return Deny(result, "APPROVAL_REQUIRED", "Control Plane の承認セッションがありません。");
			}
			try
			{
				Descriptor descriptor = JsonUtility.FromJson<Descriptor>(File.ReadAllText(descriptorPath, Encoding.UTF8));
				if (!ValidDescriptor(descriptor, projectRoot))
				{
					// Project をまたぐ認可や任意 URL への secret 送信を防ぐ。
					return Deny(result, "APPROVAL_INVALID", "承認 descriptor の Project または接続先が不正です。");
				}
				string nonce = Guid.NewGuid().ToString("N");
				RequestContext received = context == null ? null : new RequestContext { contextId = context.receivedContextId, contextFingerprint = context.receivedContextFingerprint, projectRoot = context.projectRoot, runId = context.runId };
				Request payload = review != null ? new ReviewRequest { review = review, context = received } : mutationPaths != null ? new MutationRequest { mutationPaths = mutationPaths, context = received } : new Request();
				payload.sessionId = descriptor.sessionId;
				payload.nonce = nonce;
				payload.projectRoot = projectRoot;
				payload.command = command;
				payload.planId = planId;
				payload.expectedRevision = expectedRevision;
				payload.approvalToken = approvalToken;
				payload.exactDiff = exactDiff;
				byte[] body = Encoding.UTF8.GetBytes(JsonUtility.ToJson(payload));
				byte[] secret = DecodeSecret(descriptor.secret);
				HttpWebRequest request = (HttpWebRequest)WebRequest.Create(descriptor.endpoint);
				request.Method = "POST";
				request.ContentType = "application/json; charset=utf-8";
				request.ContentLength = body.Length;
				request.Timeout = 3000;
				request.ReadWriteTimeout = 3000;
				request.Proxy = null;
				request.AllowAutoRedirect = false;
				request.Headers["X-UnityAgent-Signature"] = Sign(secret, "request\n", body);
				using (Stream stream = request.GetRequestStream())
				{
					stream.Write(body, 0, body.Length);
				}
				using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
				using (Stream stream = response.GetResponseStream())
				using (MemoryStream buffer = new MemoryStream())
				{
					byte[] chunk = new byte[4096];
					int count;
					while ((count = stream.Read(chunk, 0, chunk.Length)) > 0)
					{
						if (buffer.Length + count > 65536)
						{
							// 応答を際限なくメモリへ読み込まない。
							return Deny(result, "APPROVAL_INVALID", "承認応答が許容サイズを超えました。");
						}
						buffer.Write(chunk, 0, count);
					}
					byte[] responseBody = buffer.ToArray();
					if (!EqualSignature(Sign(secret, "response\n", responseBody), response.Headers["X-UnityAgent-Signature"]))
					{
						// 未認証の応答本文を承認結果として解釈しない。
						return Deny(result, "APPROVAL_INVALID", "承認応答の署名を検証できません。");
					}
					Response authorization = JsonUtility.FromJson<Response>(new UTF8Encoding(false, true).GetString(responseBody));
					if (authorization == null || authorization.nonce != nonce || authorization.sessionId != descriptor.sessionId || !authorization.allowed || string.IsNullOrWhiteSpace(authorization.reservationId))
					{
						// 別呼出しの正規応答も現在の承認として再利用しない。
						return Deny(result, "APPROVAL_INVALID", "承認が拒否されたか、応答の呼出し binding が一致しません。");
					}
					// 署名と呼出し binding が揃った応答だけを、Scene 変更開始の receipt として返す。
					result.authoritySessionId = descriptor.sessionId;
					result.authorityNonce = nonce;
					result.authorityReservationId = authorization.reservationId;
					return true;
				}
			}
			catch (Exception exception) when (exception is IOException || exception is WebException || exception is ArgumentException || exception is InvalidOperationException || exception is CryptographicException || exception is UnauthorizedAccessException)
			{
				// 接続失敗を承認成功へ置き換えず、secret や request 本文をエラーへ流出させない。
				return Deny(result, "APPROVAL_INVALID", "Control Plane の承認を確認できません。");
			}
		}

		private bool ValidDescriptor(Descriptor descriptor, string projectRoot)
		{
			if (descriptor == null || descriptor.schemaVersion != "1" || string.IsNullOrWhiteSpace(descriptor.projectRoot) || string.IsNullOrWhiteSpace(descriptor.secret) || !Regex.IsMatch(descriptor.secret, "\\A[0-9a-f]{64}\\z") || string.IsNullOrWhiteSpace(descriptor.sessionId) || !Regex.IsMatch(descriptor.sessionId, "\\A[0-9a-f]+\\z"))
			{
				// 構造や鍵を解釈できない descriptor で接続・認可を試みない。
				return false;
			}
			if (!Path.IsPathRooted(descriptor.projectRoot) || !string.Equals(Path.GetFullPath(descriptor.projectRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar), Path.GetFullPath(projectRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar), Application.platform == RuntimePlatform.WindowsEditor ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
			{
				// 他 Project の承認セッションを現在の Scene の権限として使わない。
				return false;
			}
			return Uri.TryCreate(descriptor.endpoint, UriKind.Absolute, out Uri endpoint) && endpoint.Scheme == "http" && endpoint.Host == "127.0.0.1" && endpoint.Port > 0 && descriptor.endpoint == "http://127.0.0.1:" + endpoint.Port + "/authorize";
		}

		private byte[] DecodeSecret(string secret)
		{
			byte[] bytes = new byte[32];
			for (int index = 0; index < bytes.Length; index++)
			{
				bytes[index] = Convert.ToByte(secret.Substring(index * 2, 2), 16);
			}
			return bytes;
		}

		private string Sign(byte[] secret, string prefix, byte[] body)
		{
			byte[] prefixBytes = Encoding.UTF8.GetBytes(prefix);
			byte[] payload = new byte[prefixBytes.Length + body.Length];
			Buffer.BlockCopy(prefixBytes, 0, payload, 0, prefixBytes.Length);
			Buffer.BlockCopy(body, 0, payload, prefixBytes.Length, body.Length);
			using (HMACSHA256 hmac = new HMACSHA256(secret))
			{
				return BitConverter.ToString(hmac.ComputeHash(payload)).Replace("-", string.Empty).ToLowerInvariant();
			}
		}

		private bool EqualSignature(string expected, string actual)
		{
			if (actual == null || actual.Length != expected.Length)
			{
				// 欠落・切断された署名を有効な応答として比較しない。
				return false;
			}
			int difference = 0;
			for (int index = 0; index < expected.Length; index++)
			{
				difference |= expected[index] ^ actual[index];
			}
			return difference == 0;
		}

		private bool Deny(ArtistResult result, string code, string reason)
		{
			result.errors.Add(new ArtistError { code = code, message = reason });
			return false;
		}
	}
}
#endif
