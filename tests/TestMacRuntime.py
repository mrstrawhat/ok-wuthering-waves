import importlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from config import config
from src.OnnxYolo8Detect import OnnxYolo8Detect
from src.task.BaseWWTask import BaseWWTask
from src.task.TacetEliminationTask import TacetEliminationTask


@pytest.mark.skipif(sys.platform != 'darwin', reason='native macOS application registry')
def test_all_native_registered_task_and_tab_modules_import():
    for module_name, class_name in config['onetime_tasks'] + config['trigger_tasks'] + config['custom_tabs']:
        assert getattr(importlib.import_module(module_name), class_name)
    assert not any('MultiAccount' in cls for _, cls in config['onetime_tasks'])


@pytest.mark.parametrize('setting, expected', [('简体中文', 'zh_CN'), ('繁體中文', 'zh_TW'), ('English', 'en_US')])
def test_native_language_selection_does_not_depend_on_windows_hwnd(setting, expected):
    task = BaseWWTask.__new__(BaseWWTask)
    task.executor = SimpleNamespace(config={'macos': {}}, device_manager=SimpleNamespace(hwnd_window=None))
    task.executor.config['macos']['bundle_id'] = 'test.game'
    task.get_global_config = lambda name: {'游戏语言': setting}
    assert task.game_lang == expected


def test_detector_restores_non_square_model_coordinates_and_clips_to_frame():
    model = OnnxYolo8Detect.__new__(OnnxYolo8Detect)
    model.preprocess_target_h, model.preprocess_target_w = 320, 640
    model.iou_threshold = .45
    model.dic_labels = {0: 'echo'}
    # Original 800x400 frame -> 640x320 model, gain .8, no letterbox padding.
    output = np.array([[[80., -8.], [80., 80.], [32., 32.], [32., 32.], [.95, .9]]], dtype=np.float32)
    boxes = model._postprocess([output], (0, 0), (400, 800), .8, 0)
    assert (boxes[0].x, boxes[0].y, boxes[0].width, boxes[0].height) == (80, 80, 40, 40)
    assert boxes[1].x == 0
    assert all(box.width > 0 and box.height > 0 for box in boxes)


def test_model_uses_cpu_and_actual_model_dimensions_on_mac():
    session = Mock()
    session.get_inputs.return_value = [SimpleNamespace(name='images', shape=[1, 3, 320, 640])]
    session.get_outputs.return_value = [SimpleNamespace(name='out', shape=[1, 5, 8400])]
    session.get_providers.return_value = ['CPUExecutionProvider']
    with patch('src.OnnxYolo8Detect.sys.platform', 'darwin'), \
         patch('src.OnnxYolo8Detect.ort.get_available_providers', return_value=['CoreMLExecutionProvider', 'CPUExecutionProvider']), \
         patch('src.OnnxYolo8Detect.ort.InferenceSession', return_value=session) as create:
        model = OnnxYolo8Detect('fixture.onnx')
    assert create.call_args.kwargs['providers'] == ['CPUExecutionProvider']
    assert (model.preprocess_target_h, model.preprocess_target_w) == (320, 640)


def test_event_drag_keeps_guarded_native_interaction():
    interaction = Mock()
    task = SimpleNamespace(executor=SimpleNamespace(config={'macos': {'bundle_id': 'test.game'}},
                                                    interaction=interaction), swipe_relative=Mock())
    TacetEliminationTask.drag_relative(task, (.3, .4), (.5, .6))
    task.swipe_relative.assert_called_once_with(.3, .4, .5, .6, duration=.6)
    interaction.hwnd_window.bring_to_front.assert_not_called()
