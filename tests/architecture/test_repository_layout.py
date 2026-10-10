import json
from pathlib import Path
import tempfile
import unittest
from tools import validate_layout as module
class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'src').mkdir();(self.root/'src/core.py').write_text('')
        self.config={'schema_version':'1.0','repository':'owner/repo','authority_map':'src/authority.yaml','allowed_roots':{'src':'product','repository-layout.json':'layout contract','.devcontainer':'optional developer container'},'canonical_paths':{'src/core.py':'product','src/authority.yaml':'authority'},'forbidden_roots':['Runtime','Tools'],'forbidden_directory_names':['backends']}
        (self.root/'src/authority.yaml').write_text('')
        (self.root/'repository-layout.json').write_text(json.dumps(self.config))
        self.tracked=['src/core.py','src/authority.yaml','repository-layout.json']
    def tearDown(self): self.tmp.cleanup()
    def errors(self,paths=None): return module.validate(self.root, self.tracked if paths is None else paths)
    def test_canonical_and_future_container_allowed(self):
        self.assertEqual([],self.errors(self.tracked+['.devcontainer/devcontainer.json']))
    def test_forbidden_root_detected_even_untracked(self):
        (self.root/'Tools').mkdir();self.assertTrue(any('forbidden root' in e for e in self.errors()))
    def test_unknown_root_and_nested_backends_rejected(self):
        self.assertTrue(any('unknown root' in e for e in self.errors(self.tracked+['Unknown/x'])))
        self.assertTrue(any('forbidden directory' in e for e in self.errors(self.tracked+['src/backends/x.py'])))
        (self.root/'src/backends').mkdir();self.assertTrue(any('forbidden directory' in e for e in self.errors()))
    def test_missing_canonical_and_ownership_rejected(self):
        (self.root/'src/core.py').unlink();self.assertTrue(any('canonical path' in e for e in self.errors()))
        self.config['allowed_roots']['src']='';(self.root/'repository-layout.json').write_text(json.dumps(self.config));self.assertTrue(any('owner' in e for e in self.errors()))
    def test_path_escape_rejected(self):
        self.config['canonical_paths']['../outside']='bad';(self.root/'repository-layout.json').write_text(json.dumps(self.config));self.assertTrue(any('confined' in e for e in self.errors()))
    def test_authority_must_remain_separate(self):
        self.config['authority_map']='repository-layout.json';(self.root/'repository-layout.json').write_text(json.dumps(self.config));self.assertTrue(any('separate' in e for e in self.errors()))
    def test_external_authored_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root/'.devcontainer').symlink_to(outside, target_is_directory=True)
            self.assertTrue(any('confined' in e for e in self.errors(self.tracked+['.devcontainer'])))
            (self.root/'src/linked').symlink_to(outside, target_is_directory=True)
            self.assertTrue(any('confined' in e for e in self.errors(self.tracked+['src/linked'])))
    def test_dangling_authored_symlink_rejected(self):
        (self.root/'src/linked').symlink_to(self.root/'missing')
        self.assertTrue(any('dangling' in e for e in self.errors(self.tracked+['src/linked'])))
if __name__=='__main__':unittest.main()
