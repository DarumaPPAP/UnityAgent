using System;
using System.Collections.Generic;
using UnityEngine;

namespace CameraWorks
{
	[RequireComponent(typeof(CameraWork))]
	public sealed class CameraWorkDemo : MonoBehaviour
	{
		private static readonly E_CAMERA_MOVE[] Presets =
		{
			E_CAMERA_MOVE.Fix, E_CAMERA_MOVE.FixPerfect, E_CAMERA_MOVE.FixShake,
			E_CAMERA_MOVE.PanRight, E_CAMERA_MOVE.TiltUp,
			E_CAMERA_MOVE.ZoomIn, E_CAMERA_MOVE.ZoomOut,
			E_CAMERA_MOVE.DollyIn, E_CAMERA_MOVE.DollyOut,
			E_CAMERA_MOVE.TrackRight, E_CAMERA_MOVE.CircleRight, E_CAMERA_MOVE.RollRight
		};

		private static readonly string[] Labels =
		{
			"フィクス", "完全フィクス", "ブレフィクス",
			"右パン", "ティルトアップ", "ズームイン", "ズームアウト",
			"ドリーイン", "ドリーアウト", "右トラック", "右サークル", "右ロール"
		};

		[SerializeField] private TextAsset _catalog;

		private CameraWork _work;
		private Camera _camera;
		private IReadOnlyList<S_CAMERA_CUT> _cuts;
		private Vector3 _originalPosition;
		private Quaternion _originalRotation;
		private float _originalFov;
		private int _selected;
		private string _current = "未選択";

		public TextAsset Catalog
		{
			set
			{
				_catalog = value;
				_cuts = null;
			}
		}

		private void Awake()
		{
			_work = GetComponent<CameraWork>();
			_camera = GetComponent<Camera>();
			_originalPosition = transform.position;
			_originalRotation = transform.rotation;
			_originalFov = _camera.fieldOfView;
			LoadCatalog();
		}

		private void LoadCatalog()
		{
			if (_cuts != null)
			{
				return;
			}

			TextAsset asset = _catalog != null ? _catalog : Resources.Load<TextAsset>("CameraWorkCuts");
			_cuts = asset != null ? CameraWorkCatalog.Parse(asset.text) : Array.Empty<S_CAMERA_CUT>();
		}

		private void ResetCamera()
		{
			_work.Stop();
			transform.SetPositionAndRotation(_originalPosition, _originalRotation);
			_camera.fieldOfView = _originalFov;
		}

		public void PlayPreset(int index)
		{
			if (index < 0 || index >= Presets.Length)
			{
				throw new ArgumentOutOfRangeException(nameof(index));
			}

			ResetCamera();
			_current = Labels[index];
			_work.Play(new S_CAMERA_CUT(0, _current, 1, new[] { new S_CAMERA_PHASE(Presets[index]) }));
		}

		public void PlayCut(int index)
		{
			LoadCatalog();
			if (index < 0 || index >= _cuts.Count)
			{
				throw new ArgumentOutOfRangeException(nameof(index));
			}

			_selected = index;
			S_CAMERA_CUT cut = _cuts[index];
			ResetCamera();
			_current = $"No.{cut.No}: {cut.Label}";
			_work.Play(cut);
		}

		private void PlayWeighted()
		{
			LoadCatalog();
			int total = 0;
			foreach (S_CAMERA_CUT cut in _cuts)
			{
				total += cut.Count;
			}

			if (total == 0)
			{
				return;
			}

			int pick = UnityEngine.Random.Range(0, total);
			for (int i = 0; i < _cuts.Count; i++)
			{
				pick -= _cuts[i].Count;
				if (pick < 0)
				{
					PlayCut(i);
					return;
				}
			}
		}

		private void OnGUI()
		{
			GUILayout.BeginArea(new Rect(12f, 12f, 495f, 340f), GUI.skin.box);
			GUILayout.Label("Camera Work Demo — 基本技法と196種類のカット");

			for (int row = 0; row < 3; row++)
			{
				GUILayout.BeginHorizontal();
				for (int column = 0; column < 4; column++)
				{
					int index = row * 4 + column;
					if (GUILayout.Button(Labels[index], GUILayout.Height(30f)))
					{
						PlayPreset(index);
					}
				}
				GUILayout.EndHorizontal();
			}

			GUILayout.Space(8f);
			GUILayout.Label($"再生中: {_current}");
			GUILayout.Label($"Phase: {_work.PhaseIndex + 1} / {(_work.IsPlaying ? "再生中" : "停止")}");

			LoadCatalog();
			GUILayout.Label($"カタログ: {_cuts.Count} 種類 / 1,166カット");

			GUILayout.BeginHorizontal();
			if (GUILayout.Button("前へ") && _cuts.Count > 0)
			{
				PlayCut((_selected + _cuts.Count - 1) % _cuts.Count);
			}
			if (GUILayout.Button("選択カット再生") && _cuts.Count > 0)
			{
				PlayCut(_selected);
			}
			if (GUILayout.Button("次へ") && _cuts.Count > 0)
			{
				PlayCut((_selected + 1) % _cuts.Count);
			}
			if (GUILayout.Button("頻度抽選") && _cuts.Count > 0)
			{
				PlayWeighted();
			}
			GUILayout.EndHorizontal();

			if (_cuts.Count > 0)
			{
				GUILayout.Label($"No.{_cuts[_selected].No}: {_cuts[_selected].Label}");
			}
			GUILayout.EndArea();
		}
	}
}
