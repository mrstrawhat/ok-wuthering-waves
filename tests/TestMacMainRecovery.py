"""Regression of the actual ensure_main recovery; sends no native input."""
import importlib
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from ok import CannotFindException
from src.task.BaseWWTask import BaseWWTask

module = importlib.import_module('src.task.BaseWWTask')


def task_for(results, probes=5):
    task = SimpleNamespace(logged_in=False, info_set=Mock(), sleep=Mock(),
                           log_info=Mock(), back=Mock(), screenshot=Mock(),
                           is_main=Mock(side_effect=results))
    def wait(predicate, **kwargs):
        task.wait_options = kwargs
        for _ in range(probes):
            if predicate():
                return True
        return False
    task.wait_until = wait
    return task


def test_mac_missing_hud_stops_esc_after_two_and_preserves_failure():
    task = task_for([False] * 5)
    with patch.object(module.sys, 'platform', 'darwin'):
        with pytest.raises(CannotFindException, match='角色栏'):
            BaseWWTask.ensure_main(task, time_out=180)
    assert task.back.call_count == 2
    assert task.wait_options['time_out'] == 30
    task.screenshot.assert_called_once_with('main_world_timeout')
    assert all(c.kwargs == {'esc': False} for c in task.is_main.call_args_list)


def test_mac_world_can_appear_after_escape_budget_is_used():
    task = task_for([False, False, False, True])
    with patch.object(module.sys, 'platform', 'darwin'):
        BaseWWTask.ensure_main(task, time_out=10)
    assert task.back.call_count == 2
    assert task.wait_options['time_out'] == 10
    task.screenshot.assert_not_called()


def test_mac_passive_wait_sends_no_escape():
    task = task_for([False, True])
    with patch.object(module.sys, 'platform', 'darwin'):
        BaseWWTask.ensure_main(task, esc=False)
    task.back.assert_not_called()


def test_windows_login_wait_keeps_existing_timeout_and_recovery():
    task = task_for([True])
    with patch.object(module.sys, 'platform', 'win32'):
        BaseWWTask.ensure_main(task, time_out=180)
    assert task.wait_options['time_out'] == 600
    task.is_main.assert_called_once_with(esc=True)


def test_no_reward_dialog_can_match_both_confirm_template_variants():
    confirm, checkbox = object(), object()
    def find(feature, **kwargs):
        if isinstance(feature, list):
            return None  # find_one refuses the duplicate matches.
        return {'confirm_btn_hcenter_vcenter': confirm,
                'confirm_btn_highlight_hcenter_vcenter': confirm,
                'skip_dialog_check': checkbox}.get(feature)
    task = SimpleNamespace(find_one=find, sleep=Mock(), click=Mock())
    assert BaseWWTask.click_skip_dialog_confirm(task)
    assert [c.args[0] for c in task.click.call_args_list] == [checkbox, confirm]
