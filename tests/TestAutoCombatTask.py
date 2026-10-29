import unittest
from unittest.mock import Mock, patch

from ok import TaskDisabledException
from src.char.BaseChar import BaseChar
from src.char.CharFactory import get_char_by_pos
from src.scene.WWScene import WWScene
from src.task.AutoCombatTask import AutoCombatTask
from src.task.BaseCombatTask import CharDeadException, NotInCombatException


class TestAutoCombatTask(unittest.TestCase):
    def setUp(self):
        self.scene = WWScene()
        self.executor = Mock(scene=self.scene, debug=False)
        self.task = AutoCombatTask(self.executor, None)
        self.task.scene = self.scene
        self.task.config = dict(self.task.default_config)
        self.task.char_config = {}
        self.task.warm_up_char_features = Mock()
        self.task.in_team_and_world = Mock(return_value=True)
        self.task.in_world = Mock(return_value=True)
        self.task.switch_healer = Mock()
        self.task.combat_end = Mock()
        self.task.find_one = Mock(return_value=None)
        self.task.ocr = Mock(return_value=[])

    def seed_combat(self):
        old_char = BaseChar(self.task, 0, char_name='old_team')
        old_char.is_current_char = True
        old_char.perform = Mock(side_effect=TaskDisabledException)
        self.task.chars = [old_char, None, None]
        self.task._in_combat = True
        self.task.in_liberation = True
        self.task.skip_combat_check = True
        self.task.cds = {'resonance': 12}
        self.task.freeze_durations = [(1, 2, 0.1)]
        self.scene.set_in_combat()
        return old_char

    def assert_combat_cleared(self):
        self.assertFalse(self.task._in_combat)
        self.assertFalse(self.task.in_liberation)
        self.assertFalse(self.task.skip_combat_check)
        self.assertFalse(self.task.in_sleep_check)
        self.assertEqual(self.task.chars, [None, None, None])
        self.assertEqual(self.task.cds, {})
        self.assertEqual(self.task.freeze_durations, [])
        self.assertFalse(self.scene.in_combat())

    def test_disable_during_rotation_cleans_up_and_propagates(self):
        old_char = self.seed_combat()

        with self.assertRaises(TaskDisabledException):
            self.task.run()

        old_char.perform.assert_called_once()
        self.assert_combat_cleared()
        self.task.combat_end.assert_not_called()
        self.task.switch_healer.assert_called_once()

    def test_disable_inside_combat_check_cleans_up_and_propagates(self):
        old_char = self.seed_combat()
        self.task.in_liberation = False
        self.scene.reset()
        self.task.check_f_break = Mock()
        self.task.on_combat_check = Mock(return_value=True)
        self.task.has_target = Mock(side_effect=TaskDisabledException)

        with self.assertRaises(TaskDisabledException):
            self.task.run()

        self.assert_combat_cleared()
        old_char.perform.assert_not_called()
        self.task.combat_end.assert_not_called()
        self.task.switch_healer.assert_not_called()

    def test_disable_between_runs_invalidates_chars_before_reentry(self):
        old_char = self.seed_combat()
        self.task._in_combat = False
        self.task.in_liberation = False
        self.task._enabled = True
        self.task.disable()
        self.task.enable()
        self.scene.reset()
        self.task.load_hotkey = Mock()
        self.task.in_team = Mock(return_value=(True, 0, 3))
        self.task.get_box_by_name = Mock()
        self.task.has_target = Mock(return_value=True)
        self.task.find_one = Mock(return_value=None)
        # Simulate an obscured portrait: no match must not revive an old char.
        self.task.find_best_match_in_box = Mock(return_value=None)
        recognized_chars = []

        def recognize(task, box, index, previous):
            self.assertIsNone(previous)
            char = get_char_by_pos(task, box, index, previous)
            char.perform = Mock(side_effect=TaskDisabledException)
            recognized_chars.append(char)
            return char

        with patch('src.task.BaseCombatTask.get_char_by_pos', side_effect=recognize):
            with self.assertRaises(TaskDisabledException):
                self.task.run()

        self.assertEqual([char.char_name for char in recognized_chars], ['unknown'] * 3)
        old_char.perform.assert_not_called()
        recognized_chars[0].perform.assert_called_once()
        self.assert_combat_cleared()

    def test_leaving_world_invalidates_combat_and_chars(self):
        old_char = self.seed_combat()
        self.task.in_team_and_world.return_value = False

        self.assertFalse(self.task.run())

        self.assert_combat_cleared()
        old_char.perform.assert_not_called()
        self.task.switch_healer.assert_not_called()

    def test_revive_item_dialog_is_closed_and_trigger_disabled(self):
        self.task.in_team_and_world.return_value = False
        self.task.ocr.return_value = ['选择复苏物品']
        self.task.screenshot = Mock()
        self.task.close_revive_popup = Mock()
        self.task.disable = Mock()
        self.assertFalse(self.task.run())
        self.task.close_revive_popup.assert_called_once()
        self.task.disable.assert_called_once()
        self.task.switch_healer.assert_not_called()

    def test_normal_polling_preserves_character_cache(self):
        char = BaseChar(self.task, 0, char_name='same_team')
        self.task.chars = [char, None, None]
        self.task.in_combat = Mock(return_value=False)

        self.assertFalse(self.task.run())
        self.scene.reset()
        self.assertFalse(self.task.run())

        self.assertIs(self.task.chars[0], char)

    def test_sleep_restores_skip_flag_after_disable(self):
        char = BaseChar(self.task, 0)
        for previous in (False, True):
            for check_combat in (False, True):
                with self.subTest(previous=previous, check_combat=check_combat):
                    self.task.skip_combat_check = previous

                    def interrupt_sleep(seconds):
                        self.assertEqual(self.task.skip_combat_check, previous or not check_combat)
                        raise TaskDisabledException()

                    self.task.sleep = interrupt_sleep
                    with self.assertRaises(TaskDisabledException):
                        char.sleep(0.1, check_combat=check_combat)
                    self.assertEqual(self.task.skip_combat_check, previous)

    def test_nested_sleep_keeps_outer_combat_check_suppressed(self):
        char = BaseChar(self.task, 0)
        flags = []

        def sleep(seconds):
            flags.append(self.task.skip_combat_check)
            if seconds == 1:
                char.sleep(0.1)
                flags.append(self.task.skip_combat_check)

        self.task.sleep = sleep
        char.sleep(1, check_combat=False)

        self.assertEqual(flags, [True, True, True])
        self.assertFalse(self.task.skip_combat_check)

    def test_outdoor_preparation_runs_once_across_idle_polls(self):
        self.task.config['Auto Approach Open World Target'] = True
        nest = Mock()
        nest.prepare_open_world_combat.return_value = {'kind': 'outdoor_tacet_discord_nest', 'target': 'row1'}
        self.executor.get_task_by_class.return_value = nest
        self.task.run_auto_combat = Mock(return_value=False)

        self.assertFalse(self.task.run())
        self.assertFalse(self.task.run())

        nest.prepare_open_world_combat.assert_called_once_with()
        self.task.run_auto_combat.assert_called_with()
        self.assertEqual(2, self.task.run_auto_combat.call_count)

    def test_outdoor_preparation_failure_disables_trigger_before_next_poll(self):
        self.task.config['Auto Approach Open World Target'] = True
        self.task._enabled = True
        nest = Mock()
        nest.prepare_open_world_combat.side_effect = RuntimeError('dungeon refused')
        self.executor.get_task_by_class.return_value = nest
        self.task.run_auto_combat = Mock()
        self.task.screenshot = Mock()

        with self.assertRaisesRegex(RuntimeError, 'dungeon refused'):
            self.task.run()

        self.task.screenshot.assert_called_once_with('auto_combat_approach_failed')
        self.assertFalse(self.task._enabled)
        self.assertFalse(self.task.config['_enabled'])
        self.task.run_auto_combat.assert_not_called()

    def test_outdoor_preparation_cancellation_propagates(self):
        self.task.config['Auto Approach Open World Target'] = True
        nest = Mock()
        nest.prepare_open_world_combat.side_effect = TaskDisabledException()
        self.executor.get_task_by_class.return_value = nest
        self.task.run_auto_combat = Mock()
        self.task.screenshot = Mock()

        with self.assertRaises(TaskDisabledException):
            self.task.run()

        self.task.screenshot.assert_not_called()
        self.task.run_auto_combat.assert_not_called()
        self.assert_combat_cleared()

    def test_one_combat_stop_saves_evidence_and_disables(self):
        self.task.config['Stop After One Combat'] = True
        self.task._enabled = True
        self.task.run_auto_combat = Mock(return_value=True)
        self.task.screenshot = Mock()

        self.assertTrue(self.task.run())

        self.task.screenshot.assert_called_once_with('auto_combat_after')
        self.assertFalse(self.task._enabled)
        self.assertFalse(self.task.config['_enabled'])

    def test_reenable_rearms_outdoor_preparation(self):
        self.task._enabled = False
        self.task._approach_attempted = True
        with patch('ok.task.task.TriggerTask.enable'):
            self.task.enable()
        self.assertFalse(self.task._approach_attempted)

    def test_one_combat_failure_is_not_reported_as_normal_end(self):
        for error in (CharDeadException('dead'), NotInCombatException('failed switch chars')):
            with self.subTest(error=type(error).__name__):
                self.setUp()
                self.task.config['Stop After One Combat'] = True
                self.task._enabled = True
                self.task.in_combat = Mock(return_value=True)
                char = Mock()
                char.perform.side_effect = error
                self.task.get_current_char = Mock(return_value=char)
                self.task.screenshot = Mock()

                self.assertTrue(self.task.run())

                self.assertFalse(self.task._enabled)
                self.assertIsNotNone(self.task._combat_failure)
                self.task.screenshot.assert_called_once_with('auto_combat_failed')
                self.task.combat_end.assert_not_called()
                self.task.switch_healer.assert_called_once()


if __name__ == '__main__':
    unittest.main()
