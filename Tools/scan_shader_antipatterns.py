#!/usr/bin/env python3
"""
Shader anti-pattern candidate scanner.

This tool performs lightweight source-pattern extraction only.
Its output is NOT a confirmed performance diagnosis. Findings must be reviewed
against compiler output, GPU architecture, workload, and runtime evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
from typing import Iterable

SUPPORTED_SUFFIXES = {".shader", ".hlsl", ".compute", ".cginc", ".glsl", ".metal"}

@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    confidence: str
    file: str
    line: int
    message: str
    matched_text: str
    manual_review_required: bool = True

PATTERNS: tuple[tuple[str, str, str, re.Pattern[str], str], ...] = (
    ("EXEC-003", "Info", "要計測", re.compile(r"\b(?:sin|cos|tan|asin|acos|atan|atan2|exp|log|sqrt)\s*\("), "Hot pathで高コスト関数が使用されている候補です。実行頻度とCompiler生成コードを確認してください。"),
    ("EXEC-004", "Low", "高確度", re.compile(r"\bpow\s*\([^,\n]+,\s*(?:2(?:\.0+)?|3(?:\.0+)?|4(?:\.0+)?)\s*\)"), "定数指数powの候補です。意味差とCompiler最適化を確認してから乗算化を検討してください。"),
    ("FLOW-004", "Info", "要計測", re.compile(r"\[(?:branch|flatten)\]|\bUNITY_(?:BRANCH|FLATTEN)\b"), "Branch hintが使用されています。正しさの制御ではなく計測対象として扱ってください。"),
    ("REG-002", "Medium", "高確度", re.compile(r"\b(?:float|half|int|uint|bool)(?:[1-4]|[1-4]x[1-4])?\s+\w+\s*\[\s*\d+\s*\]"), "固定長Local Array候補です。RegisterまたはLocal Memoryへの展開を確認してください。"),
    ("REG-003", "Info", "要計測", re.compile(r"\[(?:unroll|loop)(?:\([^\]]*\))?\]|#\s*pragma\s+(?:unroll|loop)"), "Loop展開Hintがあります。Code Size、Register、Spillを比較してください。"),
    ("MEM-005", "High", "高確度", re.compile(r"\bInterlocked(?:Add|And|CompareExchange|Exchange|Max|Min|Or|Xor)\b"), "Atomic操作候補です。競合アドレス、Wave内集約、呼び出し頻度を確認してください。"),
    ("MEM-006", "Medium", "高確度", re.compile(r"\b(?:GroupMemoryBarrier|GroupMemoryBarrierWithGroupSync|DeviceMemoryBarrier|DeviceMemoryBarrierWithGroupSync|AllMemoryBarrier|AllMemoryBarrierWithGroupSync)\b"), "Barrier候補です。必要なMemory Scopeと同期回数を確認してください。"),
    ("RASTER-002", "Medium", "高確度", re.compile(r"\bdiscard\b|\bclip\s*\("), "Alpha Test / discard候補です。処理位置、Early-Z、Overdraw、TBDR影響を確認してください。"),
    ("RASTER-003", "High", "高確度", re.compile(r"\bSV_Depth(?:GreaterEqual|LessEqual)?\b"), "Fragment Depth出力候補です。Early-ZとDepth correctnessを確認してください。"),
    ("UNITY-002", "Medium", "高確度", re.compile(r"#\s*pragma\s+(?:multi_compile|shader_feature)(?!_local)\b"), "Global Keyword候補です。Local化可否とRuntime切替を確認してください。"),
    ("UNITY-010", "Info", "要計測", re.compile(r"#\s*(?:if|elif)\s+.*\bSHADER_API_[A-Z0-9_]+\b"), "Platform macro分岐候補です。共通経路の肥大化とBackend差を確認してください。"),
)

TEXTURE_SAMPLE_PATTERN = re.compile(r"\b(?:SAMPLE_TEXTURE2D(?:_LOD|_GRAD|_BIAS)?|SAMPLE_TEXTURECUBE(?:_LOD)?|\w+\s*\.\s*Sample(?:Level|Grad|Bias|Cmp|CmpLevelZero)?)\s*\([^;\n]+")
NUMTHREADS_PATTERN = re.compile(r"\[\s*numthreads\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*\]")
PRAGMA_VARIANT_PATTERN = re.compile(r"^\s*#\s*pragma\s+(multi_compile(?:_local)?|shader_feature(?:_local)?)(?:_[a-z]+)?\s+(.+)$")

def strip_comments_preserve_lines(text: str) -> str:
    def replace_block(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")
    text = re.sub(r"/\*.*?\*/", replace_block, text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)

def scan_file(path: Path) -> list[Finding]:
    source = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = strip_comments_preserve_lines(source).splitlines()
    findings: list[Finding] = []
    for line_number, line in enumerate(lines, start=1):
        for rule_id, severity, confidence, pattern, message in PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(Finding(rule_id, severity, confidence, str(path), line_number, message, match.group(0).strip()))
        numthreads = NUMTHREADS_PATTERN.search(line)
        if numthreads:
            x, y, z = map(int, numthreads.groups())
            total = x * y * z
            if total <= 0 or total > 1024 or total % 32 != 0:
                findings.append(Finding("COMP-001", "Medium", "要計測", str(path), line_number, f"numthreads総数が{total}です。対象GPUのWave/Warp、Register、Shared Memory、Dispatch形状に対して実測してください。", numthreads.group(0)))
    sample_occurrences: dict[str, list[int]] = {}
    for line_number, line in enumerate(lines, start=1):
        match = TEXTURE_SAMPLE_PATTERN.search(line)
        if match:
            normalized = re.sub(r"\s+", "", match.group(0))
            sample_occurrences.setdefault(normalized, []).append(line_number)
    for normalized, line_numbers in sample_occurrences.items():
        for line_number in line_numbers[1:]:
            findings.append(Finding("MEM-001", "Medium", "要計測", str(path), line_number, "同一表記のTexture Sampleが複数あります。関数境界、LOD、Gradient、Compiler CSEを確認してください。", normalized[:240]))
    pragma_options: list[tuple[int, int, str]] = []
    for line_number, line in enumerate(lines, start=1):
        match = PRAGMA_VARIANT_PATTERN.match(line)
        if match:
            raw_options = [token for token in re.split(r"\s+", match.group(2).strip()) if token and not token.startswith("//")]
            pragma_options.append((line_number, max(1, len(raw_options)), line.strip()))
    product = 1
    for _, option_count, _ in pragma_options:
        product *= option_count
    if product >= 64 and pragma_options:
        findings.append(Finding("UNITY-003", "High" if product >= 256 else "Medium", "高確度", str(path), pragma_options[0][0], f"ソース上のKeyword直積上限候補は{product}です。Pass、Platform、URP built-in keywordを含むBuild Variant数は別途確認してください。", " | ".join(item[2] for item in pragma_options[:8])))
    findings.sort(key=lambda item: (item.file, item.line, item.rule_id))
    return findings

def iter_shader_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
                    yield child

def render_markdown(findings: list[Finding]) -> str:
    lines = ["# Shader Antipattern Scanner Candidates", "", "> この出力は候補抽出です。確定診断ではありません。", "", "| Rule ID | Severity | Confidence | File | Line | Message |", "|---|---|---|---|---:|---|"]
    for finding in findings:
        lines.append(f"| {finding.rule_id} | {finding.severity} | {finding.confidence} | `{finding.file.replace('|', '\\|')}` | {finding.line} | {finding.message.replace('|', '\\|')} |")
    lines.extend(["", f"候補数: **{len(findings)}**", ""])
    return "\n".join(lines)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Shader file or directory")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    files = list(iter_shader_files(args.paths))
    if not files:
        print("No supported shader files found.", file=sys.stderr)
        return 2
    findings: list[Finding] = []
    for file in files:
        try:
            findings.extend(scan_file(file))
        except OSError as exc:
            print(f"Failed to read {file}: {exc}", file=sys.stderr)
            return 3
    output = json.dumps({"schemaVersion": "1.0.0", "confirmedDiagnosis": False, "filesScanned": len(files), "findingCount": len(findings), "findings": [asdict(finding) for finding in findings]}, ensure_ascii=False, indent=2) + "\n" if args.format == "json" else render_markdown(findings)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
