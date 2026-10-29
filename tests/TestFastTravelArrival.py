from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from src.task.FastTravelTask import FastTravelTask


def travel_task(notice=False, confirm=True, arrived=True):
    point, button = object(), object()
    return SimpleNamespace(find_one=Mock(return_value=point), box_of_screen=Mock(), match=[],
        ocr=Mock(side_effect=[[point], [button] if confirm else []]),log_debug=Mock(),log_info=Mock(),
        screenshot=Mock(),click_traval_button=Mock(return_value=True),wait_ocr=Mock(return_value=notice),
        click=Mock(),wait_in_team_and_world=Mock(return_value=arrived))


def test_normal_travel_is_verified_in_world_before_reporting_success():
    task=travel_task()
    assert FastTravelTask.run(task)
    task.click.assert_not_called()
    task.wait_in_team_and_world.assert_called_once()
    task.screenshot.assert_any_call('fast_travel_arrived')


def test_known_story_exit_notice_is_confirmed_then_arrival_verified():
    task=travel_task(notice=True)
    assert FastTravelTask.run(task)
    task.click.assert_called_once()
    task.wait_in_team_and_world.assert_called_once()


def test_notice_without_a_confirm_button_sends_no_confirmation():
    task=travel_task(notice=True,confirm=False)
    with pytest.raises(RuntimeError,match='确认按钮'):
        FastTravelTask.run(task)
    task.click.assert_not_called()
    task.wait_in_team_and_world.assert_not_called()


def test_no_world_after_travel_is_failure():
    task=travel_task(arrived=False)
    with pytest.raises(RuntimeError,match='未回到大世界'):
        FastTravelTask.run(task)
    task.screenshot.assert_any_call('fast_travel_arrival_timeout')
