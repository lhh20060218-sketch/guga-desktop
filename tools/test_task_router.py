import tempfile
import unittest
from pathlib import Path

from core.daily_workflows import workflow_for
from core.task_router import choose_task_route
from core.workflow_catalog import WorkflowCatalog
from core.self_agent import TOOLS


class TaskRouterTests(unittest.TestCase):
    def test_daily_wechat_and_workflow_stay_local(self):
        self.assertEqual(choose_task_route('给微信小军发送一段自我介绍')['executor'], 'local_agent')
        flow = workflow_for('把最新会议录制上传B站')
        route = choose_task_route('把最新会议录制上传B站', workflow=flow)
        self.assertEqual(route['executor'], 'local_agent')
        self.assertEqual(route['category'], 'workflow')

    def test_complex_code_engineering_uses_dsh(self):
        route = choose_task_route('重构这个Python项目，修复多个源码文件和单元测试')
        self.assertEqual(route['executor'], 'dsh')
        self.assertEqual(route['category'], 'code')

    def test_screenshot_and_manual_local_override(self):
        self.assertEqual(choose_task_route('请按这个截图点按钮', image=True)['executor'], 'local_agent')
        self.assertEqual(choose_task_route('重构代码', backend='self')['executor'], 'local_agent')
        self.assertEqual(choose_task_route('打开记事本', backend='dsh')['executor'], 'dsh')

    def test_local_agent_can_use_video_pipeline_and_wechat_tools(self):
        names = {item['function']['name'] for item in TOOLS}
        self.assertIn('media_workflow', names)
        self.assertIn('wechat', names)
        self.assertIn('screen_share', names)


class WorkflowCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.catalog = WorkflowCatalog(Path(self.temp.name) / 'flows.db')

    def tearDown(self):
        self.temp.cleanup()

    def test_user_can_define_list_match_and_disable_workflow(self):
        flow = self.catalog.define('整理下载文件夹', '先核对，再按类型移动，最后回读。', title='下载整理')
        self.assertEqual(self.catalog.match('请整理下载文件夹')['id'], flow['id'])
        self.assertIn(flow['id'], {x['id'] for x in self.catalog.list()})
        self.catalog.disable(flow['id'])
        self.assertIsNone(self.catalog.match('请整理下载文件夹'))

    def test_repeated_success_creates_reviewable_candidate(self):
        self.assertIsNone(self.catalog.observe_local_success('打开微信给文件传输助手发日报', '成功', ['wechat']))
        candidate = self.catalog.observe_local_success('打开微信给文件传输助手发日报', '成功', ['wechat'])
        self.assertEqual(candidate['state'], 'candidate')
        self.assertIsNone(self.catalog.match('打开微信给文件传输助手发日报'))
        self.catalog.activate(candidate['id'])
        self.assertEqual(self.catalog.match('打开微信给文件传输助手发日报')['id'], candidate['id'])


if __name__ == '__main__':
    unittest.main()
