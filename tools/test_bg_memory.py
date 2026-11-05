import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.bg_memory import collect_board, MemoryReadError, read_board


class MemoryTests(unittest.TestCase):
    def test_current_client_combat_tag_is_preserved_and_drives_phase(self):
        from core.bg_log_capture import EventParser
        from core.bg_live import observed_phase
        parser = EventParser()
        parser.entities[7] = dict(CARDTYPE='GAME')
        for flag, phase in ((0, 'recruit'), (1, 'combat')):
            list(parser.feed('D 12:00:00.0 PowerTaskList.DebugPrintPower() - TAG_CHANGE Entity=7 tag=BACON_IN_COMBAT_PHASE value='+str(flag)))
            self.assertEqual(observed_phase(parser), phase)

    def test_request_includes_friendly_board_and_omits_other_fields(self):
        args = []
        card = SimpleNamespace(CardId='BG_TEST', EntityId=42, ZonePosition=1, Account='private')
        client = SimpleNamespace(GetBoardState=lambda include: args.append(include) or
                                 SimpleNamespace(Friendly=[card], Opposing=[]))
        result = collect_board(client)
        self.assertEqual(args, [True])
        self.assertEqual(result['friendly'], [dict(card_id='BG_TEST', entity_id=42, position=1)])
        self.assertNotIn('Account', str(result))

    def test_access_denied_is_not_misreported_as_missing_board(self):
        client = SimpleNamespace(GetBoardState=lambda include: None)
        with self.assertRaises(MemoryReadError) as caught:
            collect_board(client, denied=lambda: True)
        self.assertEqual(caught.exception.code, 'access_denied')

    def test_missing_board_is_not_claimed_to_prove_version_failure(self):
        client = SimpleNamespace(GetBoardState=lambda include: None)
        with self.assertRaises(MemoryReadError) as caught:
            collect_board(client)
        self.assertEqual(caught.exception.code, 'board_unavailable')

    def test_parent_preserves_worker_error_code(self):
        child = SimpleNamespace(stdout=b'{"ok":false,"code":"access_denied","error":"denied"}')
        with patch('core.bg_memory.checked_mirror'), patch('core.bg_memory.subprocess.run', return_value=child):
            with self.assertRaises(MemoryReadError) as caught:
                read_board()
        self.assertEqual(caught.exception.code, 'access_denied')


if __name__ == '__main__':
    unittest.main()
