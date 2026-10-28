"""Check isolated capture-verification setup without starting the application."""
import builtins
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import Mock

import pytest

from src.diagnostics import macos_capture_check as capture_check


MAIN = Path(__file__).resolve().parents[1] / 'main.py'


def test_prepare_profile_creates_a_separate_safe_profile(tmp_path, monkeypatch):
    original = tmp_path / 'existing-user-data'
    original.mkdir()
    user_options = original / 'Basic Options.json'
    user_options.write_text('{"Auto Start Game When App Starts": true}', encoding='utf-8')
    original_bytes = user_options.read_bytes()
    monkeypatch.setenv('OKWW_DATA_DIR', str(original))
    output = tmp_path / '中文 带空格' / 'new-check'

    resolved_output, profile = capture_check.prepare_profile(output)

    assert resolved_output == output.resolve()
    assert profile == resolved_output / 'profile'
    options = json.loads((profile / 'configs/Basic Options.json').read_text(encoding='utf-8'))
    assert options['Auto Start Game When App Starts'] is False
    assert options['Enable MCP Server'] is False
    assert options['Start/Stop'] == 'None'
    assert options['Minimize Window to System Tray when Closing'] is False
    assert user_options.read_bytes() == original_bytes
    assert original != profile and not profile.is_relative_to(original)


def test_prepare_profile_preserves_existing_output_evidence(tmp_path):
    output = tmp_path / 'check'
    output.mkdir()
    evidence = output / 'notes.txt'
    evidence.write_text('previous evidence stays intact', encoding='utf-8')
    capture_check.prepare_profile(output)
    assert evidence.read_text(encoding='utf-8') == 'previous evidence stays intact'


def test_prepare_profile_refuses_to_overwrite_an_existing_profile(tmp_path):
    output = tmp_path / 'check'
    configs = output / 'profile/configs'
    configs.mkdir(parents=True)
    settings = configs / 'Basic Options.json'
    settings.write_text('{"Start/Stop":"F12","custom":"preserve me"}', encoding='utf-8')
    evidence = output / 'result.json'
    evidence.write_text('{"existing":true}', encoding='utf-8')
    before = {path.relative_to(output): path.read_bytes()
              for path in output.rglob('*') if path.is_file()}

    with pytest.raises(SystemExit, match='拒绝覆盖'):
        capture_check.prepare_profile(output)

    after = {path.relative_to(output): path.read_bytes()
             for path in output.rglob('*') if path.is_file()}
    assert after == before


@pytest.mark.parametrize('frozen,arguments,message', [
    (False, ['--verify-tool-capture', 'out'], '仅用于打包后的 macOS'),
    (True, ['--verify-tool-capture', 'out', '--task', 'AutoCombatTask'], '不能与其他启动参数混用'),
    (True, ['--task', 'AutoCombatTask', '--verify-tool-capture', 'out'], '不能与其他启动参数混用'),
])
def test_invalid_capture_check_arguments_exit_before_application_setup(
        tmp_path, monkeypatch, frozen, arguments, message):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(sys, 'frozen', frozen, raising=False)
    monkeypatch.setattr(sys, 'argv', [str(MAIN), *arguments])
    monkeypatch.setenv('OKWW_DATA_DIR', str(tmp_path / 'existing-data'))
    prepare = Mock(side_effect=AssertionError('Rejected arguments must not create a profile'))
    monkeypatch.setattr(capture_check, 'prepare_profile', prepare)
    cwd = Path.cwd()
    import_original = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        # These imports are directly before OK(config).start() in the launcher.
        # Fail before any runtime initialization if its argument guard regresses.
        if name == 'config' or (name == 'ok' and 'OK' in fromlist):
            raise AssertionError('Invalid verification arguments reached application startup')
        return import_original(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    with pytest.raises(SystemExit, match=message):
        runpy.run_path(str(MAIN), run_name='__main__')

    prepare.assert_not_called()
    assert Path.cwd() == cwd
    assert not (tmp_path / 'existing-data').exists()
