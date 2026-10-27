# Mac 原生能力验证工具

此工具独立于 Windows 框架依赖，用于验证 macOS 原生窗口、连续截图和有限时长的输入动作。最低 macOS 14，使用 Swift 6 或更高版本工具链，无外部包依赖。

**工具不会启动或激活游戏、弹出权限申请、修改系统设置。当前代码实现不代表游戏实机验证通过。**

## 构建与离线检查

在本目录运行：

```sh
bash check.sh build
bash check.sh test
.build-native/debug/okww-mac-probe help
.build-native/debug/okww-mac-probe validate --script examples/menu-key.json --image-width 1920 --image-height 1080
python Tests/cli_smoke.py
```

测试使用 Swift Testing、模拟窗口、时钟和输入接收器，不发送真实输入，不调用截图接口。`check.sh` 为仅安装 Command Line Tools 的环境补充测试框架查找路径，并把编译缓存放在本工具的忽略目录。它使用 SwiftPM 的 native 构建模式；新版工具链可能提示该模式已弃用，后续迁移默认构建模式时需重新验证。

## 在用户方便实机验证时使用

先由用户启动游戏；工具本身不会启动游戏。每次重新启动游戏或切换窗口后，重新枚举窗口编号。默认应用标识是 `com.kurogame.mingchao`，可用 `--bundle` 指定。

```sh
.build-native/debug/okww-mac-probe status
.build-native/debug/okww-mac-probe windows
```

`status` 只读取环境、显示信息和已有权限状态。录屏或辅助功能权限不足时需要由用户在系统设置中授权实际运行工具的宿主，部分授权需要重启宿主才生效。工具不自动请求权限，也不通过其他路径绕过权限。

### 连续截图

`capture` 要求显式提供本次枚举的窗口编号以及不存在的绝对输出目录，例如：

```text
okww-mac-probe capture --window-id WINDOW_ID --seconds 3 --fps 30 --output /absolute/new-evidence-directory
```

输出 `first.png`、`last.png`、`report.json`；不采集音频。报告包含目标窗口、实际像素尺寸、ScreenCaptureKit 内容区域的原始点坐标与缩放信息、更新帧数量、抽样画面变化、近黑帧、帧间隔和帧龄的 P50/P95。元数据的点坐标不能直接作为 `--content-rect` 的像素坐标。帧龄不等于游戏接收输入的延迟；画面静止也不必然代表截图失败。

### 输入预览与执行

`input` 默认只输出预览。真实发送额外要求 `--execute` 和 `--stop-file`；执行前游戏必须已位于前台，且目标为最前面的普通窗口。不会替用户抢回焦点。

```text
okww-mac-probe input --window-id WINDOW_ID --script SCRIPT.json --image-width CAPTURE_WIDTH --image-height CAPTURE_HEIGHT
```

只有核对预览坐标和当前游戏状态后，才在上述命令追加：

```text
--execute --stop-file /absolute/existing-parent/STOP
```

创建停止文件、按 Ctrl+Option+Escape、发出 SIGINT/SIGTERM、窗口失焦/移动/缩放/消失，都会中止动作。退出前尝试释放本次按住的键和按钮。系统级强制终止（SIGKILL）无法运行清理代码，不能把它当成正常停止方式。

`--image-width` 和 `--image-height` 必须来自本次实际截图，不能沿用旧窗口尺寸。默认把整个捕获图像映射到窗口；截图无阴影。游戏内容区域有标题栏或留白时，用 `--content-rect x,y,width,height` 显式指定其在截图中的像素范围。该转换需要通过实际命中验证，不能只凭计算测试宣布可用。窗口变化后重新捕获和预览。

## 输入脚本

JSON 根字段为 `schemaVersion: 1` 与 `actions`。坐标归一化到 `[0,1]`，键名小写。

| kind | 参数 | 含义 |
| --- | --- | --- |
| `click` | `x`, `y`, 可选 `durationMs` | 左键按下并释放 |
| `drag` | `x`, `y`, `toX`, `toY`, 可选 `durationMs` | 按住左键分步拖动并释放 |
| `key` | `keys`，可选 `durationMs` | 按顺序按下组合键，逆序释放 |
| `move` | `x`, `y` | 移动到指定位置 |
| `relative_move` | `deltaX`/`deltaY` | 发送相对鼠标位移；游戏视角是否响应另行验证 |
| `scroll` | `deltaX`/`deltaY` | 像素单位滚动 |
| `wait` | `durationMs` | 有中止检查的等待 |

单项最多 5 秒，整份脚本最多 15 秒、100 项。未知字段、错误版本、越界或无穷坐标、不适用参数、未知键名会被拒绝，整份脚本验证通过后才可能发送动作。支持常用字母、数字、方向键、空格、Tab、Escape、Enter、Shift、Ctrl、F1–F4；不提供任意代码执行或任意文本输入。

`examples/menu-key.json` 仅用于校验脚本格式。在游戏里执行会按一次 Escape，可能打开或关闭菜单，必须结合当前画面决定是否执行。程序报告中的 `gameAcceptanceVerified` 始终为 `false`：输入接口返回不构成游戏接受操作的证据，需另存前后画面并核对结果。

改造计划与每次任务记录统一保存在仓库外的工作根目录，本目录仅保存工具代码、测试和使用说明。
