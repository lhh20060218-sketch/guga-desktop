"""Manual/full-auto separation; no game or network operations."""
import unittest
from core.netcut_policy import auto_netcut_decision


BOARD=dict(active=True,mine=[{}]*4,theirs=[{}]*4)


class PolicyTests(unittest.TestCase):
    def test_manual_plugin_never_auto_cuts(self):
        self.assertFalse(auto_netcut_decision(BOARD,full_auto=False,remaining=9)[0])

    def test_full_auto_skips_short_combat(self):
        short=dict(BOARD,mine=[{}]*2,theirs=[{}]*2)
        self.assertFalse(auto_netcut_decision(short,full_auto=True,remaining=9)[0])

    def test_full_auto_cuts_one_sizeable_combat_only_when_resources_allow(self):
        self.assertTrue(auto_netcut_decision(BOARD,full_auto=True,remaining=1)[0])
        self.assertFalse(auto_netcut_decision(BOARD,full_auto=True,remaining=1,already_cut=True)[0])
        self.assertFalse(auto_netcut_decision(BOARD,full_auto=True,remaining=0)[0])
        self.assertFalse(auto_netcut_decision(BOARD,full_auto=True,remaining=1,cooldown_remaining=3)[0])

if __name__=='__main__':unittest.main()
