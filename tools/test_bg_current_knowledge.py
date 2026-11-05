import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import core.bg_current_knowledge as module


class KnowledgeTests(unittest.TestCase):
    def test_shipped_snapshot_is_current_and_has_both_card_types(self):
        module._cache=None
        status=module.status()
        self.assertTrue(status['available'])
        self.assertEqual(status['patch'],'37.0.0.255130')
        self.assertGreater(status['minions'],300)
        self.assertGreater(status['spells'],70)

    def test_metadata_is_allowlisted_and_patch_is_exposed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cards.json'
            path.write_text(json.dumps(dict(schema=1,patch='37.0',source_revision='abc',cards={
                'BG_X':dict(name='测试随从',type='minion',attack=4,health=5,tier=3,text='数据')})),
                encoding='utf-8')
            with patch.object(module,'PATH',path):
                module._cache=None
                cache=module._load();cache['secret']='must-not-leak'
                self.assertEqual(module.metadata_for(['BG_X'])['BG_X']['attack'],4)
                self.assertEqual(module.status()['cards'],1)
                self.assertNotIn('must-not-leak',json.dumps(module.metadata_for(['BG_X'])))


if __name__=='__main__':unittest.main()
