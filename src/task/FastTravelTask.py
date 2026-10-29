import re
from ok import TriggerTask, Logger
from src.task.BaseWWTask import BaseWWTask

logger = Logger.get_logger(__name__)


class FastTravelTask(BaseWWTask, TriggerTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config = {'_enabled': False}
        self.name = "✈️ Fast Travel"
        self.description = 'Auto Click Fast Travel in Map'
        self.match = [re.compile(r'Travel'), '快速旅行', '前往', 'Proceed']

    def run(self):
        travel = self.find_one('gray_teleport')
        if travel:
            results = self.ocr(
                box=self.box_of_screen(0.7, 0.89, 1, 1),
                match=self.match)

            if results:
                self.log_debug("has result")
                self.screenshot('fast_travel_selected')
                if not self.click_traval_button():
                    return False
                # Story areas can ask for confirmation without the usual
                # "do not show again" checkbox. Only accept this known notice.
                if self.wait_ocr(0.24, 0.38, 0.78, 0.56,
                                 match=re.compile('离开区域将中断剧情体验|離開區域將中斷劇情體驗'),
                                 time_out=1, raise_if_not_found=False):
                    confirm = self.ocr(0.53, 0.53, 0.78, 0.68, match=['确认', '確認'])
                    if not confirm:
                        self.screenshot('fast_travel_confirm_not_found')
                        raise RuntimeError('无法定位剧情区域离开确认按钮；停止传送')
                    self.click(confirm, after_sleep=1)
                if not self.wait_in_team_and_world(time_out=30, raise_if_not_found=False):
                    self.screenshot('fast_travel_arrival_timeout')
                    raise RuntimeError('传送后未回到大世界；请检查当前提示')
                self.screenshot('fast_travel_arrived')
                self.log_info('快速旅行已完成：已返回大世界。')
                return True
