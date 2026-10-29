import unittest
import re
from unittest.mock import Mock

from ok import TaskDisabledException
from src.task.BaseCombatTask import CharRevivedException
from src.task.NightmareNestTask import NestTarget, NightmareNestTask


class FakeBox:

    def __init__(self, name, x=0, y=0, width=20, height=10):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class TestNightmareNestTask(unittest.TestCase):

    def test_nest_is_checked_before_nightmare_changes_book_scroll(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.config = {'Which to Farm': ['Nightmare Purification', 'Tacet Discord Nest']}
        task._init_queue()
        self.assertEqual(['go_nest', 'go_nest_scroll', 'go_nightmare', 'go_nightmare_scroll'],
                         [action.__name__ for action in task.queues])

    def test_capture_success_clears_combat_before_post_combat_waits(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._capture_mode = True
        task._in_combat = True
        picked = []

        task.pick_f = lambda handle_claim=True: picked.append(handle_claim)
        task.has_echo_notification = lambda: True

        def reset_to_false(reason=''):
            task._in_combat = False
            task.out_of_combat_reason = reason
            return False

        task.reset_to_false = reset_to_false

        self.assertFalse(task.on_combat_check())
        self.assertEqual([False], picked)
        self.assertFalse(task._in_combat)
        self.assertEqual('echo captured', task.out_of_combat_reason)

    def test_combat_nest_rechecks_after_pickup_in_team_and_open_world(self):
        for feature_name in ('team_close', 'fast_travel_custom'):
            with self.subTest(feature_name=feature_name):
                task = NightmareNestTask.__new__(NightmareNestTask)
                task._capture_mode = False
                task._capture_success = False
                combat_calls = []
                pickup_calls = []
                combat_results = iter([True, False])

                task.click = lambda *args, **kwargs: None
                task.wait_feature = lambda *args, **kwargs: FakeBox(feature_name)
                task.click_team_challenge = lambda: None
                task.wait_in_team_and_world = lambda *args, **kwargs: True
                task._travel_to_nest_or_skip = lambda nest: True
                task.sleep = lambda *args, **kwargs: None
                task.find_f_with_text = lambda: False
                task.run_until = lambda *args, **kwargs: None
                task.combat_once = lambda **kwargs: combat_calls.append(kwargs) or True
                task.walk_find_echo = lambda **kwargs: pickup_calls.append(kwargs) or True
                task.wait_combat = lambda **kwargs: next(combat_results)
                task.log_info = lambda *args, **kwargs: None
                task.send_key = lambda *args, **kwargs: None
                task.esc_world_confirm = lambda *args, **kwargs: None

                task.combat_nest(FakeBox('nest'))

                self.assertEqual([10, 1], [call['wait_combat_time'] for call in combat_calls])
                self.assertEqual(2, len(pickup_calls))

    def test_capture_mode_does_not_check_combat_after_pickup(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._capture_mode = True
        task.wait_combat = lambda **kwargs: self.fail('capture mode should leave after obtaining an echo')

        self.assertFalse(task._should_continue_combat_after_pickup())

    def test_unreachable_nest_is_cached_when_travel_does_not_enter_world(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._unreachable_nests = set()
        backs = []
        clicks = []
        wait_timeouts = []
        world_waits = []
        travel = FakeBox('fast_travel_custom')

        task.wait_until = lambda *args, **kwargs: wait_timeouts.append(kwargs['time_out']) or travel
        task.find_one = lambda name, **kwargs: travel if name == travel.name else None
        task.click = lambda box, **kwargs: clicks.append((box, kwargs))
        task.wait_in_team_and_world = lambda *args, **kwargs: world_waits.append(kwargs) or False
        task.back = lambda *args, **kwargs: backs.append(kwargs)
        task.log_info = lambda *args, **kwargs: None

        target = NestTarget(object(), 'go_nightmare:36:0.205')

        self.assertFalse(task._travel_to_nest_or_skip(target))
        self.assertIn(target.cache_key, task._unreachable_nests)
        self.assertEqual([1], wait_timeouts)
        self.assertEqual([(travel, {'after_sleep': 1})], clicks)
        self.assertEqual([], world_waits)
        self.assertEqual([{'after_sleep': 1}], backs)

    def test_nest_is_skipped_after_max_deaths(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._capture_mode = False
        task._capture_success = False
        task._unreachable_nests = set()
        task._nest_deaths = {}
        logs = []

        def combat_once(**kwargs):
            raise CharRevivedException('char dead')

        task.click = lambda *args, **kwargs: None
        task.wait_feature = lambda *args, **kwargs: FakeBox('team_close')
        task.click_team_challenge = lambda: None
        task.wait_in_team_and_world = lambda *args, **kwargs: True
        task.combat_once = combat_once
        task.log_info = lambda message, **kwargs: logs.append(message)
        nest = NestTarget(object(), 'go_nest:36:10')

        for _ in range(NightmareNestTask.max_nest_deaths - 1):
            task.combat_nest(nest)
            self.assertNotIn(nest.cache_key, task._unreachable_nests)
        task.combat_nest(nest)

        self.assertIn(nest.cache_key, task._unreachable_nests)
        self.assertIn('nightmare nest: died 3 times, skip this run: go_nest:36:10', logs)

    def test_travel_waits_up_to_120_seconds_for_loading(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._unreachable_nests = set()
        travel = FakeBox('fast_travel_custom')
        world_waits = []

        task.wait_until = lambda *args, **kwargs: travel
        task.find_one = lambda *args, **kwargs: None
        task.click = lambda *args, **kwargs: None
        task.wait_in_team_and_world = lambda *args, **kwargs: world_waits.append(kwargs) or True

        self.assertTrue(task._travel_to_nest_or_skip(NestTarget(object(), 'go_nest:36:10')))
        self.assertEqual([{'time_out': 120, 'raise_if_not_found': False}], world_waits)

    def test_find_nest_skips_cached_unreachable_row(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.count_re = re.compile(r"(\d{1,2})/(\d{1,2})")
        task.queues = [lambda: None]
        task._unreachable_nests = {'<lambda>:36:10'}
        task.log_info = lambda *args, **kwargs: None
        task.height_of_screen = lambda value: 1000 * value
        task.width_of_screen = lambda value: 2000 * value
        ocr_calls = []

        count_boxes = [
            FakeBox('0/36', y=200),
            FakeBox('0/36', y=300),
        ]

        def ocr(*args, **kwargs):
            ocr_calls.append((args, kwargs))
            return count_boxes

        task.ocr = ocr

        target = task.find_nest()

        self.assertIsInstance(target, NestTarget)
        self.assertIs(target.box, count_boxes[1])
        self.assertEqual('<lambda>:36:15', target.cache_key)
        self.assertEqual(1800, target.box.x)
        self.assertEqual(1, len(ocr_calls))

    def test_cache_key_ignores_small_ocr_position_jitter(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.queues = [lambda: None]
        task.height_of_screen = lambda value: 1000 * value

        first = task._make_nest_cache_key(FakeBox('0/36', y=200), '36')
        shifted = task._make_nest_cache_key(FakeBox('0/36', y=202), '36')

        self.assertEqual(first, shifted)


class TestOutdoorCombatPreparation(unittest.TestCase):
    def setUp(self):
        self.task = NightmareNestTask.__new__(NightmareNestTask)
        self.task._unreachable_nests = set()
        self.task._nest_deaths = {}
        self.task.ensure_main = Mock()
        self.task.log_info = Mock()
        self.task.get_nest_to_go = Mock(return_value=NestTarget(FakeBox('nest'), 'go_nest:36:10'))
        self.task.click = Mock()
        self.task.wait_feature = Mock(return_value=FakeBox('fast_travel_custom'))
        self.task.screenshot = Mock()
        self.task._travel_to_nest_or_skip = Mock(return_value=True)
        self.task.run_until = Mock(return_value=True)
        self.task.send_key_up = Mock()
        self.task.send_key = Mock(side_effect=AssertionError('No F or item interactions allowed'))
        self.task.combat_once = Mock(side_effect=AssertionError('Combat belongs to AutoCombatTask'))
        self.task.click_team_challenge = Mock(side_effect=AssertionError('No dungeon entry allowed'))

    def test_prepares_one_outdoor_target_without_claiming_or_combat(self):
        result = self.task.prepare_open_world_combat()

        self.assertEqual('outdoor_tacet_discord_nest', result['kind'])
        self.assertEqual('go_nest:36:10', result['target'])
        self.assertEqual(['go_nest', 'go_nest_scroll'], [step.__name__ for step in self.task.queues])
        self.task.run_until.assert_called_once()
        self.assertEqual({'time_out': 10, 'target': True, 'running': False}, self.task.run_until.call_args.kwargs)
        self.task.send_key_up.assert_called_once_with('w')
        self.task.send_key.assert_not_called()
        self.task.combat_once.assert_not_called()
        self.task.click_team_challenge.assert_not_called()
        self.assertEqual(['auto_combat_outdoor_selected', 'auto_combat_outdoor_arrived', 'auto_combat_before'],
                         [call.args[0] for call in self.task.screenshot.call_args_list])

    def test_dungeon_target_is_refused_before_travel(self):
        self.task.wait_feature.return_value = FakeBox('team_close')
        self.task.back = Mock()

        with self.assertRaisesRegex(RuntimeError, 'eight candidates'):
            self.task.prepare_open_world_combat()

        self.task._travel_to_nest_or_skip.assert_not_called()
        self.task.run_until.assert_not_called()
        self.task.click_team_challenge.assert_not_called()

    def test_missing_target_does_not_attempt_movement(self):
        self.task.get_nest_to_go.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'No unfinished outdoor'):
            self.task.prepare_open_world_combat()
        self.task.click.assert_not_called()
        self.task.run_until.assert_not_called()

    def test_failed_travel_does_not_attempt_movement(self):
        self.task._travel_to_nest_or_skip.return_value = False
        with self.assertRaisesRegex(RuntimeError, 'travel did not reach'):
            self.task.prepare_open_world_combat()
        self.task.run_until.assert_not_called()

    def test_approach_timeout_releases_movement_and_fails(self):
        self.task.run_until.return_value = False
        with self.assertRaisesRegex(RuntimeError, '10 second'):
            self.task.prepare_open_world_combat()
        self.task.send_key_up.assert_called_once_with('w')

    def test_cancelled_approach_releases_movement_and_propagates(self):
        self.task.run_until.side_effect = TaskDisabledException()
        with self.assertRaises(TaskDisabledException):
            self.task.prepare_open_world_combat()
        self.task.send_key_up.assert_called_once_with('w')


if __name__ == '__main__':
    unittest.main()
