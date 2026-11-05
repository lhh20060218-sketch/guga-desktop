import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bg_runtime_audit import all_types, check_saved_identity, sha256


class StaticAuditTests(unittest.TestCase):
    def test_changed_assembly_rejects_saved_identity(self):
        self.assertFalse(check_saved_identity({'assembly_sha256': 'old'}, 'new')['matches'])
        self.assertFalse(check_saved_identity({}, 'new')['matches'])
        self.assertTrue(check_saved_identity({'assembly_sha256': 'same'}, 'same')['matches'])

    def test_nested_types_are_not_silently_omitted(self):
        child = SimpleNamespace(NestedTypes=[])
        parent = SimpleNamespace(NestedTypes=[child])
        self.assertEqual(list(all_types(SimpleNamespace(Types=[parent]))), [parent, child])

    def test_digest_is_bound_to_exact_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'assembly'
            path.write_bytes(b'abc')
            self.assertEqual(sha256(path),
                'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')


if __name__ == '__main__':
    unittest.main()
