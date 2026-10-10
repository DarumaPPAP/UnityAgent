import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess

p = argparse.ArgumentParser(description='Read committed blobs only; never classify missing observations as evidence.')
p.add_argument('--root', type=Path, required=True)
p.add_argument('--revision', required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
def git(*args):
    return subprocess.check_output(['git', '-C', str(a.root), *args])
sha = git('rev-parse', a.revision + '^{commit}').decode().strip()
files = git('ls-tree', '-r', '--name-only', '-z', sha).decode().split('\0')[:-1]
roots = ('Context', 'ControlPlane', 'Operations', 'Orchestration', 'Persistence', 'Policy', 'Runtime', 'Eval', 'Tests', 'Tools', 'Prompt', 'SkillReferences', 'Templates', 'Specs', 'Registry', 'Schemas', 'SubAgents', 'Design', 'TestProjects', 'src/UnityArtist.Cli')
pattern = re.compile(r'(?<![\w/])(?:' + '|'.join(re.escape(x) for x in roots) + r')/[A-Za-z0-9_./*{}~-]+')
blobs, refs, groups = [], [], defaultdict(list)
for path in files:
    data = git('show', sha + ':' + path)
    digest = hashlib.sha256(data).hexdigest()
    history = path.startswith('Tests/Fixtures/Legacy/') or path.startswith('TestProjects/UnityArtistVerification-2022.3/')
    blobs.append({'path': path, 'bytes': len(data), 'sha256': digest, 'classification': 'protected_history' if history else 'active_or_review_required'})
    if data and not path.endswith('.meta'):
        groups[digest].append(path)
    try:
        content = data.decode('utf-8')
    except UnicodeDecodeError:
        continue
    for line, text in enumerate(content.splitlines(), 1):
        for match in pattern.finditer(text):
            refs.append({'file': path, 'line': line, 'reference': match.group(), 'classification': 'historical' if history else 'active_or_review_required'})
report = {'schema_version': '1.0', 'revision': sha, 'classification_note': 'Only frozen Legacy and 2022.3 fixture references are classified historical. Other references require owner review; duplicate bytes alone never authorize deletion.', 'file_count': len(files), 'root_counts': dict(sorted(Counter(x.split('/')[0] for x in files).items())), 'blobs': blobs, 'path_references': refs, 'duplicate_nonempty_non_meta_groups': [{'sha256': h, 'paths': paths} for h, paths in sorted(groups.items()) if len(paths) > 1]}
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(sha, len(files), 'files;', len(refs), 'path refs;', len(report['duplicate_nonempty_non_meta_groups']), 'duplicate groups')
