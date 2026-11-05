import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from core.bg_version import verify_same_patch

class VersionGateTests(unittest.TestCase):
    def test_modified_rule_data_blocks_engine_loading(self):
        from core.bg_selfplay import load_engine, ENGINE_REVISION
        with tempfile.TemporaryDirectory() as folder:
            with patch('core.bg_version.verify_same_patch',return_value={'patch':'37.0.0.255130'}), \
                 patch('core.bg_selfplay.subprocess.check_output',side_effect=[ENGINE_REVISION, 'data/bg_pool_minions.json']):
                with self.assertRaisesRegex(ValueError,'unrecorded'):
                    load_engine(folder)

    def test_untracked_rule_files_block_engine_loading(self):
        from core.bg_selfplay import load_engine, ENGINE_REVISION
        with tempfile.TemporaryDirectory() as folder:
            with patch('core.bg_version.verify_same_patch',return_value={'patch':'37.0.0.255130'}), \
                 patch('core.bg_selfplay.subprocess.check_output',side_effect=[ENGINE_REVISION, '', 'hsrl2/scripts/unrecorded.py']):
                with self.assertRaisesRegex(ValueError,'untracked'):
                    load_engine(folder)

    def test_mismatched_offline_patch_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir();(root/'data/bg_summary.json').write_text(json.dumps({'patch':'36.2.2.249896'}),encoding='utf-8')
            with patch('core.bg_version.client_patch',return_value='37.0.0.255130'),self.assertRaisesRegex(ValueError,'不一致'):
                verify_same_patch(root)

    def test_identical_patch_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir();(root/'data/bg_summary.json').write_text(json.dumps({'patch':'37.0.0.255130'}),encoding='utf-8')
            with patch('core.bg_version.client_patch',return_value='37.0.0.255130'):
                self.assertEqual(verify_same_patch(root)['patch'],'37.0.0.255130')

if __name__=='__main__':unittest.main()
