import unittest
from unittest.mock import Mock, patch
from src.task.BaseWWTask import BaseWWTask

class TestMacGuideCategory(unittest.TestCase):
    def test_moved_outdoor_row_uses_text_and_no_fixed_height(self):
        task = Mock()
        task.wait_ocr.return_value = [Mock(name='outdoor category')]
        with patch('src.task.BaseWWTask.sys.platform', 'darwin'):
            BaseWWTask.open_boss_book(task, 'canxiang')
        args, kwargs = task.wait_ocr.call_args
        self.assertTrue(kwargs['match'].search('残像聚落'))
        self.assertFalse(kwargs['match'].search('梦魇拔除'))
        task.click.assert_called_once_with(task.wait_ocr.return_value, after_sleep=2)
        task.click_relative.assert_not_called()
