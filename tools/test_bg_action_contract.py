import copy
import unittest
from core.bg_action_contract import compile_option
from core.bg_live import candidates, fingerprint
from tools.test_bg_live import state


class ActionContractTests(unittest.TestCase):
    def test_buy_uses_client_target_and_option_batch_without_execution(self):
        current = state()
        action = next(a for a in candidates(current) if a['kind'] == 'BUY')
        result = compile_option(current, current, action, 'recruit')
        self.assertEqual(result['fields'], dict(option_set_id=4, option_index=1,
                                               target_entity=11, sub_option=-1, board_position=0))
        self.assertFalse(result['executed'])
        self.assertFalse(result['transport_ready'])

    def test_stale_state_or_mutation_is_rejected(self):
        before = state()
        action = candidates(before)[0]
        current = copy.deepcopy(before)
        current['option_set'] += 1
        with self.assertRaises(RuntimeError):
            compile_option(before, current, action, 'recruit')
        current['fingerprint'] = fingerprint(current)
        with self.assertRaisesRegex(RuntimeError, '过期'):
            compile_option(before, current, action, 'recruit')

    def test_modified_action_and_wrong_phase_are_rejected(self):
        current = state()
        action = dict(candidates(current)[0], target=999)
        with self.assertRaisesRegex(RuntimeError, '候选'):
            compile_option(current, current, action, 'recruit')
        with self.assertRaisesRegex(RuntimeError, '招募'):
            compile_option(current, current, candidates(current)[0], 'combat')


if __name__ == '__main__':
    unittest.main()
