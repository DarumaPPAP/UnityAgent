#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Playables;

namespace UnityArtist.Tests
{
	/// <summary>全kind Gateに必要なCamera参照をタスク所有FixtureへAPI経由で配置する。</summary>
	public static class CinematicFixtureBootstrap
	{
		public static void Prepare()
		{
			string project = Directory.GetParent(Application.dataPath).FullName;
			if (!string.Equals(Path.GetFileName(project), ".artist-e2e~", StringComparison.Ordinal))
			{
				throw new InvalidOperationException("このBootstrapはタスク所有.artist-e2e~専用です。");
			}
			Type cameraType = Type.GetType("Unity.Cinemachine.CinemachineCamera, Unity.Cinemachine", false) ?? Type.GetType("Cinemachine.CinemachineVirtualCamera, Cinemachine", false);
			if (cameraType == null)
			{
				throw new InvalidOperationException("全kind GateにはCinemachine Packageが必要です。");
			}
			const string scenePath = "Assets/ArtistAuthorityFixture.unity";
			const string timelinePath = "Assets/ArtistTimelineFixture.playable";
			PlayableAsset timeline = AssetDatabase.LoadAssetAtPath<PlayableAsset>(timelinePath);
			if (timeline == null || !File.Exists(Path.Combine(project, scenePath)))
			{
				throw new InvalidOperationException("所有SceneとTimelineを先にFixtureTimelineBootstrapで準備してください。");
			}
			// 保存操作は準備時に限定し、Gate開始後のScene/Timeline hashを固定する。
			var scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
			GameObject[] directors = scene.GetRootGameObjects().Where(value => value.name == "Fixture Director").ToArray();
			if (directors.Length != 1 || directors[0].GetComponent<PlayableDirector>() == null || directors[0].GetComponent<PlayableDirector>().playableAsset != timeline)
			{
				throw new InvalidOperationException("Fixture Directorと所有Timelineの一意な関連付けが必要です。");
			}
			foreach (string name in new[] { "Fixture Cinematic Camera A", "Fixture Cinematic Camera B" })
			{
				GameObject[] matches = scene.GetRootGameObjects().Where(value => value.name == name).ToArray();
				if (matches.Length > 1)
				{
					throw new InvalidOperationException("所有Camera名が重複しています: " + name);
				}
				GameObject camera = matches.Length == 0 ? new GameObject(name) : matches[0];
				if (camera.GetComponent(cameraType) == null)
				{
					camera.AddComponent(cameraType);
				}
			}
			EditorSceneManager.MarkSceneDirty(scene);
			if (!EditorSceneManager.SaveScene(scene, scenePath))
			{
				throw new InvalidOperationException("所有Cinematic Fixtureを保存できませんでした。");
			}
			AssetDatabase.SaveAssets();
			Debug.Log("所有Cinematic全kind Fixture準備完了");
		}
	}
}
#endif
