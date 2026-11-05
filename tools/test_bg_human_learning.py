import json,unittest
from pathlib import Path
from unittest.mock import patch
from core.bg_human_learning import load,advisory

class HumanLearningTests(unittest.TestCase):
    def test_current_build_model_has_metrics_and_cases(self):
        data=load();self.assertIsNotNone(data);self.assertEqual(data['client_build'],254477)
        self.assertEqual(len(data['weights']),data['feature_dim']);self.assertEqual(len(data['cases']),data['groups'])
        self.assertFalse(data['metrics']['deployable'])

    def test_advice_is_build_gated(self):
        state=dict(client_build=254477,round=10,tier=3)
        result=advisory(state,[dict(kind='BUY')]);self.assertTrue(result['available']);self.assertFalse(result['model_deployable'])
        self.assertFalse(advisory(dict(state,client_build=255130),[dict(kind='BUY')])['available'])

if __name__=='__main__':unittest.main()
