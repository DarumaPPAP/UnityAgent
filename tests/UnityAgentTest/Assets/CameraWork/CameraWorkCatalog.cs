using System;
using System.Collections.Generic;
using System.Globalization;

namespace CameraWorks
{
	public static class CameraWorkCatalog
	{
		private static readonly (string Text, E_CAMERA_MOVE Move)[] Tokens =
		{
			("フィクス（完全）", E_CAMERA_MOVE.FixPerfect),
			("フィクス（ブレ）", E_CAMERA_MOVE.FixShake),
			("右下トラック", E_CAMERA_MOVE.TrackRightDown),
			("左下トラック", E_CAMERA_MOVE.TrackLeftDown),
			("右上トラック", E_CAMERA_MOVE.TrackRightUp),
			("左上トラック", E_CAMERA_MOVE.TrackLeftUp),
			("ティルトアップ", E_CAMERA_MOVE.TiltUp),
			("ティルトダウン", E_CAMERA_MOVE.TiltDown),
			("ドリーアウト", E_CAMERA_MOVE.DollyOut),
			("ドリーイン", E_CAMERA_MOVE.DollyIn),
			("ズームアウト", E_CAMERA_MOVE.ZoomOut),
			("ズームイン", E_CAMERA_MOVE.ZoomIn),
			("右下パン", E_CAMERA_MOVE.PanRightDown),
			("左下パン", E_CAMERA_MOVE.PanLeftDown),
			("右上パン", E_CAMERA_MOVE.PanRightUp),
			("左上パン", E_CAMERA_MOVE.PanLeftUp),
			("右サークル", E_CAMERA_MOVE.CircleRight),
			("左サークル", E_CAMERA_MOVE.CircleLeft),
			("右トラック", E_CAMERA_MOVE.TrackRight),
			("左トラック", E_CAMERA_MOVE.TrackLeft),
			("上トラック", E_CAMERA_MOVE.TrackUp),
			("下トラック", E_CAMERA_MOVE.TrackDown),
			("右ロール", E_CAMERA_MOVE.RollRight),
			("左ロール", E_CAMERA_MOVE.RollLeft),
			("右パン", E_CAMERA_MOVE.PanRight),
			("左パン", E_CAMERA_MOVE.PanLeft),
			("フィクス", E_CAMERA_MOVE.Fix),
		};

		public static IReadOnlyList<S_CAMERA_CUT> Parse(string tsv)
		{
			if (string.IsNullOrWhiteSpace(tsv))
			{
				throw new ArgumentException("Camera work catalog is empty.", nameof(tsv));
			}

			var cuts = new List<S_CAMERA_CUT>();
			string[] lines = tsv.Replace("\r", "").Split('\n');

			for (int row = 1; row < lines.Length; row++)
			{
				if (string.IsNullOrWhiteSpace(lines[row]))
				{
					continue;
				}

				string[] cells = lines[row].Split('\t');
				if (cells.Length != 3 || !int.TryParse(cells[0], NumberStyles.None, CultureInfo.InvariantCulture, out int no)
					|| !int.TryParse(cells[2], NumberStyles.None, CultureInfo.InvariantCulture, out int count)
					|| no != cuts.Count + 1 || count < 1)
				{
					throw new FormatException($"Invalid catalog row {row + 1}.");
				}

				cuts.Add(new S_CAMERA_CUT(no, cells[1], count, ParsePhases(cells[1])));
			}

			return cuts.AsReadOnly();
		}

		public static S_CAMERA_PHASE[] ParsePhases(string description)
		{
			if (string.IsNullOrWhiteSpace(description))
			{
				throw new ArgumentException("A description is required.", nameof(description));
			}

			// 原表の誤記と速度・CG注記を除き、順序（→）と同時動作を保持する。
			string normalized = description.Replace("ドリアーアウト", "ドリーアウト")
				.Replace("超スピード", "").Replace("CG特殊", "").Replace("早", "");
			string[] stages = normalized.Split('→');
			var phases = new S_CAMERA_PHASE[stages.Length];

			for (int stage = 0; stage < stages.Length; stage++)
			{
				string phrase = stages[stage].Trim();
				var moves = new List<E_CAMERA_MOVE>();
				int index = 0;

				while (index < phrase.Length)
				{
					if (char.IsWhiteSpace(phrase[index]))
					{
						index++;
						continue;
					}

					bool matched = false;
					foreach (var token in Tokens)
					{
						if (index + token.Text.Length > phrase.Length
							|| string.CompareOrdinal(phrase, index, token.Text, 0, token.Text.Length) != 0)
						{
							continue;
						}

						moves.Add(token.Move);
						index += token.Text.Length;
						matched = true;
						break;
					}

					if (!matched)
					{
						throw new FormatException($"Unknown camera work at '{phrase.Substring(index)}' in '{description}'.");
					}
				}

				if (moves.Count == 0)
				{
					throw new FormatException($"Empty camera work phase in '{description}'.");
				}

				phases[stage] = new S_CAMERA_PHASE(moves.ToArray());
			}

			return phases;
		}
	}
}
