"""Build an unsigned Apple Silicon app using scripts/build_macos.py."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
datas = [(str(root / path), path) for path in ('assets', 'icons', 'i18n', 'src')]
binaries, hidden = [], []
for package in ('onnxocr', 'qfluentwidgets', 'qframelesswindow'):
    package_data, package_bin, package_imports = collect_all(package)
    datas += package_data
    binaries += package_bin
    hidden += package_imports
for package in ('ok-script', 'onnxocr-ppocrv5', 'onnxruntime', 'pyappify', 'pynput'):
    datas += copy_metadata(package)
hidden += collect_submodules('src', filter=lambda name: not any(
    excluded in name for excluded in ('MultiAccount', 'MouseResetTask', 'OpenVinoYolo8Detect')))
hidden += collect_submodules('ok.ui.qt')
hidden += ['AppKit', 'Quartz', 'ScreenCaptureKit', 'onnxruntime', 'pynput.keyboard._darwin',
           'pynput.mouse._darwin', 'ok.device.capture_methods.macos',
           'ok.device.interaction_methods.macos']
a = Analysis([str(root / 'main.py')], pathex=[str(root), str(root.parent / 'ok-script')],
    binaries=binaries, datas=datas, hiddenimports=hidden,
    excludes=['openvino', 'win32api', 'win32gui', 'win32con', 'pydirectinput', 'pycaw'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OK-WW', console=False,
          target_arch='arm64', codesign_identity=None)
collected = COLLECT(exe, a.binaries, a.datas, name='OK-WW')
app = BUNDLE(collected, name='OK-WW.app', bundle_identifier='io.github.mrstrawhat.ok-ww',
    info_plist={'CFBundleDisplayName': 'OK-WW', 'LSMinimumSystemVersion': '15.2',
                'NSHighResolutionCapable': True})
