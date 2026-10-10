"""Build hooks copy authored runtime resources into the distributable package."""
from pathlib import Path
import hashlib
import json
import shutil
from setuptools import setup, Command
from setuptools.command.editable_wheel import editable_wheel
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent

def copy_resources(destination):
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    manifest = {}
    paths = []
    for base in ('src/unityagent', '.agents', 'docs/standards', 'docs/templates', 'docs/architecture/specifications'):
        paths.extend((ROOT / base).rglob('*'))
    paths.extend(ROOT / p for p in ('VERSION', 'src/unityagent/contracts/unityagent-layer-contract.yaml', 'eval/datasets/behavior/production-tool-runtime-environment-matrix.yaml'))
    for source in sorted(set(paths)):
        relative = source.relative_to(ROOT)
        if not source.is_file() or (source.name != 'VERSION' and source.suffix not in {'.yaml', '.yml', '.json', '.md', '.txt', '.cs'}) or any(part in {'_resources', '__pycache__'} for part in relative.parts):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest[relative.as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'resource-manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n', encoding='utf-8')

class BuildPy(build_py):
    def run(self):
        super().run()
        copy_resources(Path(self.build_lib) / 'unityagent/_resources')

class BuildResources(Command):
    user_options = []
    def initialize_options(self): pass
    def finalize_options(self): pass
    def run(self): copy_resources(ROOT / 'src/unityagent/_resources')

class EditableWheel(editable_wheel):
    def run(self):
        copy_resources(ROOT / 'src/unityagent/_resources')
        super().run()

if __name__ == '__main__':
    setup(cmdclass={'build_py': BuildPy, 'build_resources': BuildResources, 'editable_wheel': EditableWheel})
