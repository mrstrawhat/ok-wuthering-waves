"""Close a recognized game menu using the existing vision/input implementations."""
import json
import time
from pathlib import Path

import cv2
import numpy as np

from ok.device.capture_methods.macos import MacOSCaptureMethod
from ok.device.interaction_methods.pynput import PynputInteraction
from ok.feature.Box import Box
from ok.feature.FeatureSet import FeatureSet


class MacMenuTask:
    def __init__(self, assets, bundle_id='com.kurogame.mingchao'):
        self.capture = MacOSCaptureMethod(bundle_id)
        self.interaction = PynputInteraction(self.capture, self.capture)
        self.features = FeatureSet(False, str(assets), .002, .002, default_threshold=.8)

    def find_close(self, frame):
        self.features.check_size(frame)
        self.features.ensure_feature('btn_dialog_close')
        template = self.features.feature_dict['btn_dialog_close'].mat
        height, width = frame.shape[:2]
        region = Box(width * .88, 0, width * .12, height * .15)
        candidates = []
        # macOS game UI scale differs from the Windows asset; keep the original
        # asset and matcher, and search a bounded set of UI scales.
        for scale in (.7, .75, .8, .85, .9, .95, 1):
            scaled = cv2.resize(template, None, fx=scale, fy=scale)
            candidates.extend(self.features.find_one_feature(
                frame, 'btn_dialog_close', template=scaled, box=region,
                threshold=.8, limit=1))
        return max(candidates, key=lambda b: b.confidence, default=None)

    def run(self, output):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        started = time.monotonic()
        self.capture.activate()
        before = self.capture.get_frame()
        cv2.imwrite(str(output / 'before.png'), before)
        button = self.find_close(before)
        if button is None:
            raise RuntimeError('No recognized close button; no input was sent')
        annotated = before.copy()
        cv2.rectangle(annotated, (button.x, button.y),
                      (button.x + button.width, button.y + button.height), (0, 255, 0), 4)
        cv2.imwrite(str(output / 'recognized.png'), annotated)
        print(f'RECOGNIZED btn_dialog_close confidence={button.confidence:.3f} '
              f'pixel_center={button.center()}', flush=True)
        if not self.capture.is_foreground():
            raise RuntimeError('Game lost focus; no input was sent')
        clicked_at = time.monotonic()
        self.interaction.click(*button.center(), down_time=.08)
        print('CLICK sent through original PynputInteraction', flush=True)
        deadline = time.monotonic() + 6
        confirmations = 0
        height, width = before.shape[:2]
        header = (slice(round(height * .025), round(height * .085)),
                  slice(round(width * .05), round(width * .20)))
        while time.monotonic() < deadline:
            time.sleep(.25)
            after = self.capture.get_frame()
            cv2.imwrite(str(output / 'after.png'), after)
            change = float(np.mean(cv2.absdiff(before, after)))
            header_change = float(np.mean(cv2.absdiff(before[header], after[header])))
            lit_fraction = float(np.mean(cv2.cvtColor(after, cv2.COLOR_BGR2GRAY) > 20))
            # A disappearing button during a fade is insufficient. Wait for
            # two lit frames with a changed menu heading after the transition.
            changed = (time.monotonic() - clicked_at >= 1 and change > 10
                       and header_change > 15 and lit_fraction > .6)
            confirmations = confirmations + 1 if changed else 0
            if confirmations >= 2:
                report = {
                    'success': True, 'function': 'close_recognized_menu',
                    'recognition': 'ok.feature.FeatureSet + existing btn_dialog_close asset',
                    'input': 'ok.device.interaction_methods.pynput.PynputInteraction.click',
                    'capture': 'ok.device.capture_methods.macos.MacOSCaptureMethod',
                    'confidence': float(button.confidence),
                    'pixel_center': button.center(),
                    'screen_point': self.capture.get_abs_cords(*button.center()),
                    'menu_header_changed': True, 'header_pixel_change': header_change,
                    'lit_fraction': lit_fraction, 'confirmed_frames': confirmations,
                    'mean_pixel_change': change,
                    'click_to_verified_seconds': time.monotonic() - clicked_at,
                    'total_seconds': time.monotonic() - started,
                }
                (output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(json.dumps(report), flush=True)
                return report
        raise RuntimeError('Click was sent, but menu closure was not verified; see after.png')
