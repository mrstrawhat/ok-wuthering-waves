import time

from ok import TriggerTask, Logger, TaskDisabledException
from src.char.CharFactory import char_names
from src.scene.WWScene import WWScene
from src.task.BaseCombatTask import BaseCombatTask, NotInCombatException, CharDeadException

logger = Logger.get_logger(__name__)


class AutoCombatTask(BaseCombatTask, TriggerTask):
    owns_switch_healer_config = True
    _reset_combat_on_run = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config = {'_enabled': True}
        self.trigger_interval = 0.1
        self.name = "⚔️ Auto Combat"
        self.description = "Enable auto combat in Abyss, Game World etc"
        self.last_is_click = False
        self.default_config.update({
            'Auto Target': True,
            'Use Liberation': True,
            'Check Levitator': True,
            'Switch to Healer before and after Combat': True,
            'Auto Approach Open World Target': False,
            'Stop After One Combat': False,
        })
        self.config_description = {
            'Auto Target': 'Turn off to enable auto combat only when manually target enemy using middle click',
            'Use Liberation': 'Do not use Liberation in Open World to Save Time',
            'Check Levitator': 'Toggle the levitator and verify if the character is floating',
            'Switch to Healer before and after Combat': 'Better Chance to Keep Character Alive',
            'Auto Approach Open World Target': '前往一处未完成的野外残像聚落并接敌一次；不是最近野怪寻路，不进入副本、不领取奖励。',
            'Stop After One Combat': '一次战斗结束或中断后关闭自动战斗；不代表已确认击杀。',
        }
        self.op_index = 0
        self.char_features_warmed_up = False
        self._approach_attempted = False
        self._combat_failure = None

    def enable(self):
        if not self._enabled:
            self._approach_attempted = False
        super().enable()

    def disable(self):
        # The UI thread only invalidates state; the executor performs the reset.
        self._reset_combat_on_run = True
        self._approach_attempted = False
        super().disable()

    def reset_auto_combat(self, reason):
        self._reset_combat_on_run = False
        self.reset_to_false(reason)
        self.chars = [None, None, None]
        self.freeze_durations = []

    def warm_up_char_features(self):
        if self.char_features_warmed_up:
            return
        try:
            for char_name in char_names:
                self.get_feature_by_name(char_name)
        except Exception as e:
            logger.warning(f'warm_up_char_features failed: {e}')
            return
        self.char_features_warmed_up = True
        logger.info(f'warm_up_char_features loaded {len(char_names)} character templates')

    def run(self):
        if self._reset_combat_on_run:
            self.reset_auto_combat('auto combat restarted')
        try:
            if self.config.get('Auto Approach Open World Target') and not self._approach_attempted:
                # Set before calling the helper: errors must not cause the next
                # trigger poll to navigate or teleport again.
                self._approach_attempted = True
                from src.task.NightmareNestTask import NightmareNestTask
                nest_task = self.get_task_by_class(NightmareNestTask)
                if nest_task is None:
                    raise RuntimeError('NightmareNestTask is not registered')
                prepared = nest_task.prepare_open_world_combat()
                self.info_set('Open World Target', prepared)
                self.log_info(f'Prepared outdoor nest for AutoCombatTask: {prepared}')
            result = self.run_auto_combat()
            if result and self.config.get('Stop After One Combat'):
                if self._combat_failure:
                    self.screenshot('auto_combat_failed')
                    self.log_error(f'Combat failed: {self._combat_failure}; auto combat disabled.')
                else:
                    self.screenshot('auto_combat_after')
                    self.log_info('本次战斗循环结束，自动战斗已关闭；尚未据此确认击杀。')
                self.disable()
            return result
        except TaskDisabledException:
            self.reset_auto_combat('auto combat disabled')
            raise
        except Exception:
            if self.config.get('Auto Approach Open World Target'):
                try:
                    self.screenshot('auto_combat_approach_failed')
                finally:
                    self.disable()
            raise

    def run_auto_combat(self):
        self.warm_up_char_features()
        self._combat_failure = None
        ret = False
        if not self.scene.in_team(self.in_team_and_world):
            # A dead party slot opens a consumable dialog. Never leave the
            # trigger polling there or allow a later rotation to confirm it.
            if self.find_one('revive_confirm_hcenter_vcenter', threshold=0.8) or self.ocr(
                    0.16, 0.18, 0.48, 0.3,
                    match=['选择复苏物品', '選擇復甦物品']):
                self.screenshot('auto_combat_revive_item_refused')
                self.close_revive_popup()
                self.log_error('角色死亡：已关闭复苏物品窗口，停止自动战斗，不使用消耗品。')
                self.disable()
            self.reset_auto_combat('not in team and world')
            return ret
        self.use_liberation = self.config.get('Use Liberation')
        if not self.use_liberation and not self.in_world():  # 仅大世界生效
            self.use_liberation = True
        combat_start = time.time()
        switched_to_healer = False
        while self.in_combat():
            ret = True
            try:
                if not switched_to_healer:
                    self.switch_healer()
                    switched_to_healer = True
                self.get_current_char().perform()
            except CharDeadException:
                self._combat_failure = 'Characters dead'
                self.log_error(f'Characters dead', notify=True)
                break
            except NotInCombatException as e:
                if 'failed switch chars' in str(e):
                    self._combat_failure = str(e)
                logger.info(f'auto_combat_task_out_of_combat {int(time.time() - combat_start)} {e}')
                break
        if ret and self._combat_failure is None:
            self.combat_end()
            self.switch_healer()
        return ret

    def realm_perform(self):
        if not self.last_is_click:
            if self.op_index % 10 == 0:
                self.send_key_and_wait_animation('4', self.in_illusive_realm, enter_animation_wait=0.2)
            else:
                self.click()
        else:
            if self.available('liberation'):
                self.send_key_and_wait_animation(self.get_liberation_key(), self.in_illusive_realm)
            elif self.available('echo'):
                self.send_key(self.get_echo_key())
            elif self.available('resonance'):
                self.send_key(self.get_resonance_key())
            elif self.is_con_full() and self.in_team()[0]:
                self.send_key_and_wait_animation('2', self.in_illusive_realm)
        self.last_is_click = not self.last_is_click
        self.op_index += 1
        self.sleep(0.02)


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=AutoCombatTask, debug=True)
