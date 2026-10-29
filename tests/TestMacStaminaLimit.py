from types import SimpleNamespace
from unittest.mock import Mock, patch
import importlib
import pytest
from ok import CannotFindException
from src.task.BaseWWTask import BaseWWTask
module = importlib.import_module('src.task.BaseWWTask')


def run_claim(current, spent=0, popup=False, must_use=180):
    app=SimpleNamespace(mac_stamina_spent=spent)
    task=SimpleNamespace(sleep=Mock(),get_stamina=lambda:(current,480,current+480),
        get_global_config=lambda name:{'本次运行普通波片上限':180,'允许使用储备波片':False},
        click_dialog_right_button=Mock(),click_dialog_left_button=Mock(),
        wait_feature=Mock(return_value=popup),info_set=Mock(),log_info=Mock())
    with patch.object(module.sys,'platform','darwin'), patch.object(module,'og',SimpleNamespace(my_app=app)):
        try:
            result=BaseWWTask.use_stamina(task,once=60,must_use=must_use)
        except CannotFindException:
            result=None
    return task,app,result


def test_normal_waveplates_can_use_double_within_budget():
    task,app,result=run_claim(240)
    assert result[1]==120 and app.mac_stamina_spent==120
    task.click_dialog_right_button.assert_called_once()


def test_remaining_budget_forces_single_even_when_double_is_affordable():
    task,app,result=run_claim(240,spent=120)
    assert result[1]==60 and app.mac_stamina_spent==180
    assert result[0] is False
    task.click_dialog_left_button.assert_called_once()
    task.click_dialog_right_button.assert_not_called()


def test_exhausted_budget_cannot_confirm_any_reward_cost():
    task,app,result=run_claim(240,spent=180)
    assert result is None and app.mac_stamina_spent==180
    task.click_dialog_left_button.assert_not_called()
    task.click_dialog_right_button.assert_not_called()


def test_reserve_balance_cannot_make_an_unaffordable_claim():
    task,app,result=run_claim(0)
    assert result is None and app.mac_stamina_spent==0
    task.click_dialog_left_button.assert_not_called()
    task.click_dialog_right_button.assert_not_called()


def test_top_up_dialog_is_never_confirmed():
    task,app,result=run_claim(120,popup=True)
    assert result is None and app.mac_stamina_spent==0
