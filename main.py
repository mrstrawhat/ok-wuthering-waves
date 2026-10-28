if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path

    capture_check_output = None
    if any(arg.startswith('--verify-tool-capture') for arg in sys.argv[1:]):
        if sys.platform != 'darwin' or not getattr(sys, 'frozen', False):
            raise SystemExit('--verify-tool-capture 仅用于打包后的 macOS 应用。')
        if len(sys.argv) != 3 or sys.argv[1] != '--verify-tool-capture':
            raise SystemExit('用法：OK-WW --verify-tool-capture OUT；不能与其他启动参数混用。')
        from src.diagnostics.macos_capture_check import prepare_profile
        capture_check_output, capture_check_profile = prepare_profile(sys.argv[2])
        os.environ['OKWW_DATA_DIR'] = str(capture_check_profile)
        # The framework must not interpret any task/MCP arguments in this mode.
        sys.argv = [sys.argv[0]]

    if sys.platform == 'darwin':
        if getattr(sys, 'frozen', False):
            data_dir = Path(os.environ.get('OKWW_DATA_DIR') or
                            Path.home() / 'Library' / 'Application Support' / 'OK-WW').expanduser().resolve()
            data_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(data_dir)
        else:
            os.chdir(Path(__file__).resolve().parent)
    from config import config
    from ok import OK

    config = config
    if capture_check_output is not None:
        config['my_app'] = ['src.diagnostics.macos_capture_check', 'CaptureCheck']
        config['tool_capture_check_output'] = str(capture_check_output)
        config['mcp'] = {'enabled': False}
    ok = OK(config)
    ok.start()
