# 极速进程管家 v1.1.0

轻量 Windows 进程与功耗监控工具。单文件 Python（标准库 + tkinter），双击即用。

## 功能

- 分组查看进程，未响应置顶，可直接结束或重启
- CPU、内存、GPU、NPU、磁盘、网络、温度总览
- **Intel RAPL 实时功耗**：CPU Package、CPU 核心、DRAM（**不需要管理员权限**）
- 平均值、峰值、约 3 分钟滚动曲线，以及一条会自动适应的功耗参考线

## 自动识别本机 CPU（v1.1.0 起）

不再写死某一个型号，换任何一台电脑都能用：

1. 先读注册表 `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0\ProcessorNameString`，失败再用 WMI `Win32_Processor` 兜底；
2. 内置对照表覆盖 Panther Lake / Lunar Lake / Arrow Lake / Meteor Lake / Raptor Lake / Alder Lake / Core Ultra-U / Ryzen 移动版 的基础功耗（PL1）与最大睿频功耗（PL2 / MTP）；
3. 表里没有的型号按核心后缀（HX / H / P / U / V）估算；
4. 曲线参考线取**「查表值」与「本机实测峰值」中的较大者**：实测超过官方值时参考线自动上移，并标注为「实测峰值」；
5. 想手工指定？在脚本目录放一个 `power_limit.txt`，内容 `25 80`（基础 / 最大，单位 W），或只写一个数表示最大功耗。

功耗页头部会显示识别到的 CPU 型号，右下角显示功耗上限的依据来源。

## 运行

```bat
:: 依赖（只需一次）
pip install pywin32

:: 启动
::   双击 启动极速进程管家.cmd
::   或
pythonw process_manager.py
::   或直接打开功耗页
pythonw process_manager.py --power
```

- Python 3.10+（需要自带 tkinter 的官方发行版）；
- `pywin32` 仅用于读取 RAPL 功耗传感器，缺了不影响进程管理功能。

## 功耗读数说明

- 数据源：Windows 性能计数器 `Win32_PerfFormattedData_PowerMeterCounter_EnergyMeter`（Intel RAPL）；
- 传感器名按 `Package / PKG`、`PP0`、`DRAM` 关键字自动匹配，不同平台命名不一样也能适配；
- 非 Intel 平台或计数器 / 驱动未启用时，功耗页会给出明确提示，其余功能不受影响；
- 参考线只是「官方规格 + 实测峰值」的提示，不会对系统做任何限频或修改。

## 使用提示

- 建议从开始菜单 / 桌面快捷方式启动：从普通终端启动的 GUI 会继承终端的 DPI 感知级别，在 150% 缩放的屏幕上字会偏小。
- 把快捷方式固定到任务栏时，请从**开始菜单右键固定**；从运行中的窗口右键固定，Windows 只会记下 `pythonw.exe` 而丢掉脚本参数，点了会没反应。

## 更新日志

- **v1.1.0**
  - CPU 型号与功耗上限自动识别，去掉写死的 `258V / 37W`；
  - RAPL 传感器名动态匹配，兼容不同平台命名；
  - 参考线支持「实测峰值」自适应，并显示依据来源；
  - 新增 `--power` 启动参数，直接进入功耗页；
  - 窗口 / 任务栏图标使用自带 `极速进程管家.ico`。
- v1.0.0：首个版本。
