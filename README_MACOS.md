# Mac 源码版

本分支在原项目上接入原生 macOS 截图和前台输入，保留原任务与素材。
完整进度和验收清单位于两个仓库外的 `macOS兼容改造计划书.md`。

## 安装与启动

当前锁定环境：Apple Silicon、macOS 15.2 或更新、Python 3.12。
把改造后的 `ok-script` 与本项目放在同一个父目录：

```text
工作目录/
  ok-script/
  ok-wuthering-waves/
```

1. 双击 `安装Mac版.command`，安装到本项目的 `.venv`，不会启动游戏。
2. 手动打开游戏。可保持全屏；工具不会强制改成窗口模式。
3. 双击 `启动Mac版.command`，在原界面选择 Mac 鸣潮设备。
4. 在权限卡片检查录屏和辅助功能权限。授权对象随启动方式而定，可能是 Terminal 或 Python；变更后重开工具。
5. 确认游戏语言与“Mac 游戏设置”一致，再手动开始所需任务。

已有安装包缓存时，可以离线安装：

```sh
.venv/bin/python scripts/install_macos.py --offline --wheel-dir ../.dependency-wheels
```

F9（可配置为 F10/F11/F12）控制开始/暂停。全局快捷键另需输入监控权限；
未允许时仅在工具窗口内有效。切出游戏会停止后续操作并释放本工具按住的键鼠，返回后需手动恢复。

源码版配置、日志、截图保存在项目目录。打包版保存在 `~/Library/Application Support/OK-WW/`，不会写入应用包。

## 可选应用包构建

```sh
.venv/bin/python -m pip install -r requirements-macos-build.txt
.venv/bin/python scripts/build_macos.py
```

输出 `dist/OK-WW.app`。构建配置已提供；打包和应用包首次权限仍待集中验证，当前没有已公证的发布包。

## 当前边界

代码已接入原设备、识别、OCR/ONNX、输入和任务调度；代码完成不等于游戏功能验收通过。
全屏基本点击的既有实测不代表战斗、日常和所有素材均通过；集中游戏验收仍待进行。
Windows 多账号、Windows 计划任务、桌面 QQ/微信自动通知、悬浮绘制和 Windows 自动更新在 Mac 不开放。
