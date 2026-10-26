#if UNITY_EDITOR && !ARTIST_AUTHORITY_STANDALONE
using System;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;

namespace UnityArtist.Tests
{
	internal sealed class SceneFixture : IDisposable
	{
		private readonly Scene previous;
		private readonly Scene owned;
		internal string Folder { get; }
		internal string ScenePath { get; }

		internal SceneFixture()
		{
			previous = SceneManager.GetActiveScene();
			string name = "__ArtistTests_" + Guid.NewGuid().ToString("N");
			Folder = "Assets/" + name;
			AssetDatabase.CreateFolder("Assets", name);
			ScenePath = Folder + "/Owned.unity";
			string template = AssetDatabase.GUIDToAssetPath("ff73b1c709394616a71376df21c30e98");
			if (string.IsNullOrEmpty(template) || !AssetDatabase.CopyAsset(template, ScenePath))
			{
				throw new InvalidOperationException("テスト所有Sceneを保存できませんでした。");
			}
			owned = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Additive);
			SceneManager.SetActiveScene(owned);
		}

		public void Dispose()
		{
			if (previous.IsValid() && previous.isLoaded)
			{
				SceneManager.SetActiveScene(previous);
			}
			if (owned.IsValid() && owned.isLoaded)
			{
				EditorSceneManager.CloseScene(owned, true);
			}
			// GUID付き専用領域だけが所有物であり、既存SceneやAssetは削除しない。
			if (Folder.StartsWith("Assets/__ArtistTests_", StringComparison.Ordinal) && AssetDatabase.IsValidFolder(Folder))
			{
				AssetDatabase.DeleteAsset(Folder);
			}
		}
	}
}
#endif
