"""Verify the frozen tool's own window through the production capture backend.

This check never starts a task, sends input, or activates a capture target.
"""
import json
import os
from pathlib import Path
import sys
import time

from ok import og
from src.globals import Globals


def prepare_profile(output):
    """Create an isolated profile atomically; preserve previous check evidence."""
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    profile = output / 'profile'
    try:
        profile.mkdir()
    except FileExistsError:
        raise SystemExit(f'验收配置已存在，拒绝覆盖：{profile}') from None
    configs = profile / 'configs'
    configs.mkdir()
    options = {'Auto Start Game When App Starts': False, 'Enable MCP Server': False,
        'Start/Stop': 'None', 'Minimize Window to System Tray when Closing': False}
    (configs / 'Basic Options.json').write_text(
        json.dumps(options, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return output, profile


class CaptureCheck(Globals):
    """Use the existing main-window hook and stop normally after a bounded check."""
    MAX_SECONDS = 20

    def __init__(self, exit_event):
        super().__init__(exit_event)
        self.exit_event = exit_event
        self.output = Path(og.config['tool_capture_check_output'])
        self.capture = None
        self.window = None
        self.last_frame = None
        self.finished = False
        self.timer = None
        self.watchdog = None
        self.started = None
        self.result = {'passed': False, 'frozen': bool(getattr(sys, 'frozen', False)),
            'executable': sys.executable, 'pid': os.getpid(), 'game_started': False,
            'game_activated': False, 'input_sent': False, 'frames': [], 'errors': [],
            'profile': str(self.output / 'profile'), 'attempts': 0}

    def on_show_main_window(self, window):
        from PySide6.QtCore import QTimer
        self.window = window
        self.started = time.monotonic()
        self.timer = QTimer(window)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._attempt)
        self.watchdog = QTimer(window)
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self._timed_out)
        self.watchdog.start(self.MAX_SECONDS * 1000)
        # The hook runs before show(); let normal show/bring_to_front and paint
        # events run first. Do not activate another app to make the check pass.
        self.timer.start(400)

    def _native_window(self):
        import AppKit
        import objc
        assert self.window.isVisible(), 'Main window is not visible yet'
        view = objc.objc_object(c_void_p=int(self.window.winId()))
        native = view.window()
        assert native is not None, 'Qt does not yet have a native NSWindow'
        application = AppKit.NSRunningApplication.currentApplication()
        assert int(application.processIdentifier()) == os.getpid()
        assert application.isActive(), 'The tool process has not become active'
        return native, str(application.bundleIdentifier())

    def _check_identity(self, native):
        window_id = int(native.windowNumber())
        assert int(self.capture.window.owningApplication().processID()) == os.getpid(), \
            'Capture selected another process'
        assert int(self.capture.window.windowID()) == window_id, \
            'Capture did not select the Qt main window'
        return window_id

    def _attempt(self):
        if self.finished:
            return
        if self.exit_event.is_set() or time.monotonic() - self.started >= self.MAX_SECONDS:
            self._timed_out()
            return
        self.result['attempts'] += 1
        try:
            import cv2
            from ok.device.capture_methods import macos as capture_module
            native, bundle_id = self._native_window()
            self.result['bundle_id'] = bundle_id
            self.result['framework_module_path'] = capture_module.__file__
            if self.capture is None:
                self.capture = capture_module.MacOSCaptureMethod(bundle_id, self.exit_event)
            else:
                self.capture.refresh_window()
            window_id = self._check_identity(native)
            rect = native.frame()
            scale = float(native.backingScaleFactor())
            expected = (round(rect.size.width * scale), round(rect.size.height * scale))
            if len(self.result['frames']) < 3:
                frame = self.capture.do_get_frame()
                if self.finished:
                    return
                self._check_identity(self._native_window()[0])
                assert frame is not None, 'Capture returned no frame'
                size = (int(frame.shape[1]), int(frame.shape[0]))
                stats = {'mean': float(frame.mean()), 'std': float(frame.std()),
                    'min': int(frame.min()), 'max': int(frame.max())}
                assert size == expected, f'Wrong frame dimensions: {size}, native window: {expected}'
                assert stats['max'] > 0 and stats['std'] > 5, f'Black or empty frame: {stats}'
                assert time.monotonic() - self.started < self.MAX_SECONDS, 'Capture exceeded check deadline'
                path = self.output / f'frame-{len(self.result["frames"]) + 1:02d}.png'
                assert cv2.imwrite(str(path), frame), 'Could not save captured frame'
                self.last_frame = frame
                self.result['frames'].append({'path': str(path), 'size': size,
                    'expected_native_size': expected, 'native_scale': scale, 'pixels': stats,
                    'window_id': window_id, 'window_title': str(native.title()),
                    'capture_window_title': str(self.capture.window.title()), 'pid': os.getpid()})
            if len(self.result['frames']) == 3:
                rows = og.executor.ocr_lib().ocr(self.last_frame)
                if self.finished:
                    return
                words = [str(row[1][0]) for page in (rows or []) for row in (page or [])
                    if len(row) > 1 and row[1] and isinstance(row[1][0], str)]
                self.result['ocr_text'] = words
                matched = [word for word in words if 'okww' in ''.join(
                    character for character in word.casefold() if character.isalnum())]
                self.result['ocr_product_title'] = matched
                assert matched, 'OCR did not find the fixed OK-WW product title'
                assert time.monotonic() - self.started < self.MAX_SECONDS, 'OCR exceeded check deadline'
                self.result['mcp_server_running'] = og.ok._mcp_server is not None
                assert not self.result['mcp_server_running'], 'MCP must stay disabled'
                self._finish(True)
                return
        except Exception as error:
            self.result['errors'].append({'attempt': self.result['attempts'],
                'type': type(error).__name__, 'message': str(error),
                'elapsed_seconds': round(time.monotonic() - self.started, 3)})
        if not self.finished:
            if time.monotonic() - self.started >= self.MAX_SECONDS:
                self._timed_out()
            else:
                self.timer.start(350)

    def _timed_out(self):
        if not self.finished:
            self.result['failure'] = 'Tool capture check did not complete within 20 seconds'
            self._finish(False)

    def _finish(self, passed):
        from ok.core.events import communicate
        if self.finished:
            return
        self.finished = True
        self.timer.stop()
        self.watchdog.stop()
        if self.capture is not None:
            try:
                self.capture.close()
            except Exception as error:
                self.result['errors'].append({'type': type(error).__name__,
                    'message': str(error), 'stage': 'capture cleanup'})
        self.result['passed'] = passed
        self.result['elapsed_seconds'] = round(time.monotonic() - self.started, 3)
        self.result['normal_exit_requested'] = True
        try:
            temporary = self.output / 'result.json.tmp'
            temporary.write_text(json.dumps(self.result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            temporary.replace(self.output / 'result.json')
        finally:
            communicate.quit.emit()
