"""Social gaze stays preview-only and never owns facial expression state."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ui.attention_preview import AttentionPreview

class AttentionTests(unittest.TestCase):
    def test_near_cursor_can_get_attention_then_expires(self):
        c=AttentionPreview(seed=1)
        for _ in range(20):c.update(.05,.5,.2)
        self.assertEqual(c.state,'following')
        for _ in range(120):c.update(.05,.5,.2)
        self.assertEqual(c.target,(0.,0.))
        self.assertEqual(c.state,'idle')

    def test_distant_or_busy_cursor_does_not_capture_attention(self):
        c=AttentionPreview(seed=1)
        for _ in range(100):c.update(.05,4,4)
        self.assertEqual(c.target,(0.,0.))
        for _ in range(100):c.update(.05,.5,.2,busy=True)
        self.assertEqual(c.target,(0.,0.))

    def test_leaving_cursor_releases_attention(self):
        c=AttentionPreview(seed=1)
        for _ in range(20):c.update(.05,.5,.2)
        c.update(.05,4,4)
        self.assertEqual(c.state,'returning');self.assertEqual(c.target,(0.,0.))

if __name__=='__main__':unittest.main()
