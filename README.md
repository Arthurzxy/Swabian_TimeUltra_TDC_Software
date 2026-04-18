# Swabian TimeUltra TDC Software

基于 `PyQt5` 的 Swabian `Time Tagger Ultra` 上位机工具，用于采集 Start/Stop 直方图、显示实时计数率，并对 SPAD 测试结果进行快速分析与导出。

当前主程序是 `TDC_SPAD_Analyzer.py`。

## 功能概览

- 连接和断开 `Time Tagger Ultra`
- 配置 `Start/Stop` 通道、阈值、甄别方向、TDC 死时间
- 采集 `Histogram / Time Response`
- 测量过程中实时刷新曲线
- 支持手动停止当前采集
- 计算 `PDE`、`APP`、`Jitter`
- `DCR` 由界面输入框直接填写
- 按测试条件自动命名并导出 CSV

## 仓库说明

本仓库 **不包含** Swabian `Time Tagger` 驱动、安装包、离线文档和 `Time Tagger Lab` 软件文件。这些内容请从 Swabian Instruments 官网下载后，放到项目本地的 `Time Tagger/` 目录中使用。

这样做的目的是：

- 降低仓库体积
- 避免分发第三方软件包带来的合规风险
- 让驱动版本由使用者自行控制

## 运行环境

- Windows 10/11 x64
- Python 3.10+
- 已安装或可用的 Python 包：
  - `PyQt5`
  - `numpy`
  - `matplotlib`
- 可用的 Swabian `Time Tagger` 软件包

## 从 Swabian 官网下载驱动和软件

官方来源：

- 下载页：
  `https://www.swabianinstruments.com/time-tagger/downloads/`
- 安装说明：
  `https://www.swabianinstruments.com/static/documentation/TimeTagger/gettingStarted/installation.html`

我刚才核对的是 Swabian 官方页面。该页面在 `2026-03-26` 标注了 `Time Tagger 2.21.2`，并提供 Windows 安装包下载。

建议下载流程：

1. 打开 Swabian 官方下载页
2. 在 `Time Tagger Series - Software` 中选择 `Windows`
3. 下载并安装官方软件包
4. 将本项目运行所需内容放到项目根目录下的 `Time Tagger/` 中

本程序启动时会从以下位置查找资源：

- `Time Tagger/driver/python`
- `Time Tagger/driver/x64` 或 `Time Tagger/driver/x86`
- `Time Tagger/driver/firmware`

如果你直接使用官方安装目录，也可以手动把所需子目录复制到本项目的 `Time Tagger/` 下。

目标结构示例：

```text
Time Tagger/
├─ driver/
│  ├─ firmware/
│  ├─ python/
│  ├─ x64/
│  └─ x86/
├─ documentation/
└─ Time Tagger Lab/
```

## 快速开始

1. 安装 Python 依赖

```powershell
pip install PyQt5 numpy matplotlib
```

2. 准备本地 `Time Tagger` 软件目录

- 按上面的官方链接下载 Swabian 软件包
- 将所需目录放到项目根目录 `Time Tagger/`

3. 启动程序

```powershell
python TDC_SPAD_Analyzer.py
```

4. 在界面中完成以下流程

- 选择 `Start` / `Stop` 通道
- 设置阈值、甄别方向、`TDC` 死时间
- 点击“连接设备”
- 设置采样参数
- 点击“开始测量”
- 如需提前结束，点击“停止测量”
- 采集结束后点击“分析数据”
- 确认结果后点击“保存数据”

## 界面参数说明

### 硬件配置

- `Start 通道` / `Stop 通道`：硬件输入通道
- `阈值 (mV)`：触发电平
- `甄别方向`：上升沿或下降沿触发
- `TDC死时间 (ps)`：写入 Time Tagger 输入通道的 deadtime

### 测试参数

- `Bin宽度 (ps)`：Histogram 单个 bin 的时间宽度
- `Bin数量`：Histogram 的总 bin 数
- `采集时间 (s)`：单次采集持续时间
- `光频率 (Hz)`：用于 `PDE` 计算
- `SPAD死时间 (us)`：用于 `APP` 计算
- `DCR (Hz)`：当前版本中由用户直接输入，不从 TDC Histogram 自动反推

### 分析结果

- `PDE`：探测效率
- `APP`：后脉冲概率
- `Jitter`：主峰半峰宽，单位 `ps`

### 测试条件

- `温度`
- `偏压`
- `门幅`

这些值会写入导出的文件名和 CSV 元数据。

## 数据分析逻辑

当前版本的分析入口在 `TDC_SPAD_Analyzer.py` 中。

### PDE

程序会先找到 Histogram 主峰，然后向左右扩展，累加主峰区域内 `count > 1000` 的计数，得到 `PC`。

计算公式：

```text
pde_ratio = PC / (采集时间 * 光频率)
PDE = -ln(1 - pde_ratio) * 100
```

### APP

程序会取 Histogram 最后 `20%` 的 bin 平均值作为背景 `DC`，再从

```text
主峰时间 + SPAD死时间
```

之后开始累加尾部计数，得到 `TC` 和对应 bin 数 `N`。

计算公式：

```text
APP = (TC - DC * N) / PC * 100
```

### DCR

当前版本中：

```text
DCR = 界面输入框中的 DCR (Hz)
```

也就是说，`DCR` 不是从 TDC 直方图中自动计算出来的。

### Jitter

当前版本将 `Jitter` 定义为主峰的 `FWHM`。

处理方式：

- 先取尾部均值作为背景
- 计算半高值
- 在主峰左右两侧寻找半高交点
- 使用线性插值修正半高交点位置
- `Jitter = 右半高点 - 左半高点`

## 导出结果

导出的 CSV 文件名包含以下测试条件和结果：

- `Temp`
- `Bias`
- `Gate`
- `DCR`
- `PDE`
- `APP`
- 日期

CSV 中同时包含：

- 测试元数据
- Histogram 时间轴
- Histogram 计数数据

## 目录说明

```text
.
├─ .gitignore
├─ README.md
├─ TDC_SPAD_Analyzer.py
└─ Time Tagger/
   └─ README.md
```

## 说明

- `TDC-analysis.py` 已从仓库跟踪中移除，并被加入 `.gitignore`
- `Time Tagger` 软件包文件不再纳入仓库跟踪
- 测量过程中可以手动停止，停止后会保留当前已采集到的数据
- 如果 `TimeTagger` 库未成功加载，程序仍可启动，但硬件连接功能不可用
