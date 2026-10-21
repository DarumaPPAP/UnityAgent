"""既存メソッドのreturn式だけを置換し、宣言とSerialized契約を保持する。"""
import hashlib
from pathlib import Path
import re
import stat

from unityagent.persistence.store.atomic_store import sha256_json
from unityagent.runtime.sandbox.workspace_guard import snapshot_workspace_hashes

_LITERAL_OR_COMMENT = re.compile(r'//[^\r\n]*|/\*[\s\S]*?\*/|@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_RETURN = re.compile(r'return[ \t]+[A-Za-z0-9_ .()+*/%<>=!&|^?:,\-]+;')
_METHOD = re.compile(r'[A-Za-z_][\w<>,?.\[\] \t\r\n]*\s+[A-Za-z_]\w*\s*\([^{};]*\)\s*$')


def project_revision(project):
    project = Path(project).resolve(strict=True)
    return sha256_json({name: snapshot_workspace_hashes(project / name)
                        for name in ('Assets', 'Packages', 'ProjectSettings')})


def validate_csharp_patch(source, expected_text, replacement_text):
    if (not all(isinstance(value, str) and value for value in (source, expected_text, replacement_text))
            or expected_text == replacement_text or source.count(expected_text) != 1):
        raise ValueError('C# patch needs one exact, changed preimage')
    for snippet in (expected_text, replacement_text):
        if (len(snippet) > 1024 or not _RETURN.fullmatch(snippet)
                or any(value in snippet for value in ('//', '/*', '\r', '\n'))):
            raise ValueError('C# patch is limited to one existing return expression')
    start = source.index(expected_text)
    masked = _LITERAL_OR_COMMENT.sub(lambda match: ' ' * len(match.group()), source)
    if masked[start:start + len(expected_text)] != expected_text:
        raise ValueError('C# patch cannot target a comment or literal')
    stack = []
    boundary = 0
    for index, character in enumerate(masked[:start]):
        if character == '{':
            signature = masked[boundary:index].strip()
            stack.append(bool(_METHOD.fullmatch(signature)))
            boundary = index + 1
        elif character == '}':
            if not stack:
                raise ValueError('C# source has unmatched structural boundaries')
            stack.pop()
            boundary = index + 1
        elif character == ';':
            boundary = index + 1
    if not any(stack):
        raise ValueError('C# patch must be inside an existing method body')
    return source[:start] + replacement_text + source[start + len(expected_text):]


def source_target(project, relative_path):
    from unityagent.runtime.sandbox.workspace_guard import confined_path, normalize_relative_path
    project = Path(project).resolve(strict=True)
    if normalize_relative_path(relative_path) != relative_path:
        raise ValueError('C# source path must be canonical')
    if not relative_path.startswith('Assets/') or not relative_path.endswith('.cs'):
        raise ValueError('C# patch requires an Assets source file')
    lexical = project / relative_path
    target = confined_path(project, relative_path, require_file=True)
    # Scopeは入力名だけでなく実体にも適用する。ディレクトリaliasも拒否する。
    if target != lexical or any(path.is_symlink() for path in [lexical, *lexical.parents] if path != project and project in path.parents):
        raise ValueError('C# source aliases are outside the bounded patch contract')
    info = target.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('C# source must be an unaliased regular file')
    return target


def patch_revisions(project, relative_path, expected_text, replacement_text):
    target = source_target(project, relative_path)
    source = target.read_bytes().decode('utf-8')
    updated = validate_csharp_patch(source, expected_text, replacement_text)
    before = {name: snapshot_workspace_hashes(Path(project) / name) for name in ('Assets', 'Packages', 'ProjectSettings')}
    after = {name: dict(values) for name, values in before.items()}
    after['Assets'][relative_path.removeprefix('Assets/')] = hashlib.sha256(updated.encode('utf-8')).hexdigest()
    return {'expected_revision': sha256_json(before), 'result_revision': sha256_json(after),
            'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
            'result_source_sha256': hashlib.sha256(updated.encode('utf-8')).hexdigest()}
