# 极速进程管家 v1.3.0

轻量 Windows 进程与功耗监控工具。单文件 Python（标准库 + tkinter），双击即用。

## 功能

- 分组查看进程，未响应置顶，可直接结束或重启
- CPU、内存、GPU、NPU、磁盘、网络、温度总览
- **Intel RAPL 实时功耗**：CPU Package、CPU 核心、DRAM（**不需要管理员权限**）
- **温度 / 散热页**：多源温度读取 + 假传感器识别 + 散热限制与降频原因
- 平均值、峰值、约 3 分钟滚动曲线，以及一条会自动适应的功耗参考线

## 温度 / 散热（v1.3.0 新增）

顶部标签页「温度 / 散热」，命令行加 `--temp` 可直接打开。

- **四张卡片**：温度读数、可信度、CPU 封装功耗（RAPL）、降频原因。
- **明细表**：每个传感器的来源、实例名、读数、判定；同时列出 `% Passive Limit`（被动散热限制）与 `Throttle Reasons`（降频原因，按位解码成「温度 / 功耗 / 电流 / 其他」）。
- **静态假传感器识别**：连续采样对比「温度变化」与「CPU 负载变化」——若温度纹丝不动（跨度 < 0.3 °C）而负载大幅波动（跨度 > 25%），判定为 **静态 · 疑似假传感器**，顶栏显示 `CPU温 28°C(静态·不可信)`，不再把假值当真温度。
- **真实 CPU 温度**：自动探测 `root\LibreHardwareMonitor` 与 `root\OpenHardwareMonitor`。装了 [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) 并开启其 WMI 提供程序后，本程序会优先采用硬件直读温度（判定显示「可信（硬件直读）」）。
- 为什么需要这一步：不少笔记本（实测 REDMI Book Pro 16 2026 / Panther Lake）固件只暴露**一个** ACPI 热区，而且读数**恒定**——CPU 封装功耗从 13 W 拉到 62 W，它始终是 27.9 °C。这不是程序读错，是硬件没提供；本程序会明确标注，而不是伪造一个会动的数字。

## 自动识别本机 CPU（v1.1.0 起，v1.2.0 继续加强）

不再写死某一个型号，换任何一台电脑都能用：

1. 先读注册表 `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0\ProcessorNameString`，失败再用 WMI `Win32_Processor` 兜底；
2. 内置对照表覆盖 Panther Lake / Lunar Lake / Arrow Lake / Meteor Lake / Raptor Lake / Alder Lake / Core Ultra-U / Ryzen 移动版（Ryzen AI Max、Ryzen AI 300、HS/H/U），以及桌面平台（Raptor Lake-K、Alder Lake-K、Ryzen 7000X / 5000X 等）的基础功耗（PL1）与最大睿频功耗（PL2 / MTP）；
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
::   或直接打开温度 / 散热页
pythonw process_manager.py --temp
```

- Python 3.10+（需要自带 tkinter 的官方发行版）；
- `pywin32` 仅用于读取 RAPL 功耗传感器，缺了不影响进程管理功能。

## 功耗读数说明

- 数据源：Windows 性能计数器 `Win32_PerfFormattedData_PowerMeterCounter_EnergyMeter`（Intel RAPL）；
- 传感器名按 `Package / PKG`、`PP0`、`DRAM` 关键字自动匹配，不同平台命名不一样也能适配；
- 非 Intel 平台或计数器 / 驱动未启用时，功耗页会给出明确提示，其余功能不受影响；
- 参考线只是「官方规格 + 实测峰值」的提示，不会对系统做任何限频或修改。

## 温度读数说明（v1.3.0）

- 数据源按顺序尝试：① LibreHardwareMonitor / OpenHardwareMonitor 的 WMI 传感器（真值，优先）→ ② `Win32_PerfFormattedData_Counters_ThermalZoneInformation`（ACPI 热区，一次调用约 13 ms）；
- 采样与进程/GPU 指标同一线程，每 3 秒一轮，不额外常驻进程；
- 判定逻辑只做「是否随负载变化」这一件事，不猜测、不外推，读不到就显示「--」或「无可用温度源」。

## 使用提示

- 建议从开始菜单 / 桌面快捷方式启动：从普通终端启动的 GUI 会继承终端的 DPI 感知级别，在 150% 缩放的屏幕上字会偏小。
- 把快捷方式固定到任务栏时，请从**开始菜单右键固定**；从运行中的窗口右键固定，Windows 只会记下 `pythonw.exe` 而丢掉脚本参数，点了会没反应。

## 更新日志

- **v1.3.0**
  - 新增「温度 / 散热」标签页（`--temp`）：温度读数 / 可信度 / 封装功耗 / 降频原因四张卡片 + 传感器明细表（含 `% Passive Limit`、`Throttle Reasons`）；
  - **静态假传感器识别**：温度不随负载变化时标注为「静态 · 疑似假传感器」，顶栏显示 `(静态·不可信)`，不再把假值当真温度；
  - 自动探测 LibreHardwareMonitor / OpenHardwareMonitor，装了就读硬件真值并优先采用；
  - 修复：温度源从 4 次 `Get-Counter`（约 4.2 秒）改为一次 `Win32_PerfFormattedData_Counters_ThermalZoneInformation`（约 13 毫秒），避免采样命令超过 12 秒超时、判定卡在「判定中…」；
  - 修复：温度读数显示 `0.0 °C` 的二次换算 bug。
- **v1.2.0**
  - 机型适配继续加强：对照表补上桌面平台（Raptor Lake-K / Alder Lake-K / Ryzen 7000X / 5000X 等）；
  - 某个 RAPL 传感器（核心 / DRAM）读不到时，对应卡片显示 `—`，不再给出误导性的 `0.00 W`。
- **v1.1.0**
  - CPU 型号与功耗上限自动识别，去掉写死的 `258V / 37W`；
  - RAPL 传感器名动态匹配，兼容不同平台命名；
  - 参考线支持「实测峰值」自适应，并显示依据来源；
  - 新增 `--power` 启动参数，直接进入功耗页；
  - 窗口 / 任务栏图标使用自带 `极速进程管家.ico`。
- v1.0.0：首个版本。
