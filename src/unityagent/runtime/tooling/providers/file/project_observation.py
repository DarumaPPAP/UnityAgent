"""Serialized Project設定だけを観測し、実行中Editorの状態と区別する。"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from unityagent.runtime.sandbox.workspace_guard import WorkspaceGuardError, confined_path


class UniqueMappingLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(f"duplicate serialized key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def inspect_project_files(root: Path) -> dict:
    sources = {}
    limitations = ["Serialized configuration only; runtime quality selection and script overrides are not observed."]

    def read(relative):
        path = confined_path(root, relative, require_file=True)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError(f"observation file exceeds 2 MiB: {relative}")
        content = path.read_bytes()
        sources[relative] = {"path": relative, "sha256": hashlib.sha256(content).hexdigest()}
        text = content.decode("utf-8-sig")
        text = re.sub(r"^%[^\n]*\n", "", text, flags=re.MULTILINE)
        text = re.sub(r"^--- !u!\d+ &-?\d+\s*$", "---", text, flags=re.MULTILINE)
        value = yaml.load(text, Loader=UniqueMappingLoader)
        if not isinstance(value, dict):
            raise ValueError(f"serialized mapping required: {relative}")
        return value

    version = read("ProjectSettings/ProjectVersion.txt").get("m_EditorVersion")
    if not isinstance(version, str) or not version:
        raise ValueError("ProjectVersion has no observed Unity version")

    def classify(reference):
        if not isinstance(reference, dict) or type(reference.get("fileID")) is not int:
            raise ValueError("render pipeline reference is absent or invalid")
        if reference["fileID"] == 0:
            # 明示null参照だけをBuilt-inと判断する。設定欠落をnullへ変換しない。
            return "builtin"
        guid = reference.get("guid")
        if not isinstance(guid, str) or not re.fullmatch(r"[a-f0-9]{32}", guid):
            raise ValueError("render pipeline GUID is invalid")
        matches = []
        for count, meta in enumerate((root / "Assets").rglob("*.asset.meta"), 1):
            if count > 50000:
                raise ValueError("pipeline GUID lookup exceeds 50000 asset metadata files")
            relative = meta.relative_to(root).as_posix()
            safe = confined_path(root, relative, require_file=True)
            if safe.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("asset metadata exceeds observation limit")
            if re.search(r"^guid:\s*" + re.escape(guid) + r"\s*$", safe.read_text(encoding="utf-8-sig"), re.MULTILINE):
                matches.append(relative)
        if len(matches) != 1:
            raise ValueError("render pipeline GUID has no unique Assets mapping")
        read(matches[0])
        asset = read(matches[0][:-5]).get("MonoBehaviour")
        script = asset.get("m_Script") if isinstance(asset, dict) else None
        if not isinstance(script, dict) or not isinstance(script.get("guid"), str):
            raise ValueError("render pipeline asset has no script GUID")
        families = []
        known_scripts = (("urp", "com.unity.render-pipelines.universal", "Runtime/Data/UniversalRenderPipelineAsset.cs.meta"), ("hdrp", "com.unity.render-pipelines.high-definition", "Runtime/RenderPipeline/HDRenderPipelineAsset.cs.meta"))
        for family, package, script_path in known_scripts:
            package_roots = [root / "Packages" / package, *(root / "Library/PackageCache").glob(package + "@*")]
            for package_root in package_roots:
                candidate = package_root / script_path
                if candidate.is_file() and read(candidate.relative_to(root).as_posix()).get("guid") == script["guid"]:
                    families.append(family)
        if len(set(families)) != 1:
            raise ValueError("render pipeline script does not uniquely match a local URP/HDRP package")
        return families[0]

    pipeline = "unknown"
    try:
        graphics = read("ProjectSettings/GraphicsSettings.asset").get("GraphicsSettings")
        quality = read("ProjectSettings/QualitySettings.asset").get("QualitySettings")
        if not isinstance(graphics, dict) or not isinstance(quality, dict):
            raise ValueError("GraphicsSettings or QualitySettings mapping is missing")
        default = graphics.get("m_CustomRenderPipeline")
        levels = quality.get("m_QualitySettings")
        if not isinstance(levels, list) or not levels:
            raise ValueError("quality level settings are missing")
        default_family = classify(default)
        families = {default_family}
        for level in levels:
            override = level.get("customRenderPipeline") if isinstance(level, dict) else None
            family = classify(override)
            families.add(default_family if family == "builtin" else family)
        if len(families) != 1:
            raise ValueError("configured quality levels have different render pipeline families")
        pipeline = next(iter(families))
    except (WorkspaceGuardError, OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        limitations.append(str(exc))
    return {"unity_version": version, "render_pipeline": pipeline, "observation_scope": "serialized_project_configuration", "sources": list(sources.values()), "known_limitations": limitations, "runtime_evaluation": "NOT_EVALUATED_RUNTIME"}
