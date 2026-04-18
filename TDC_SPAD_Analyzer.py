"""
TDC SPAD 分析软件
功能：
1. 连接Time Tagger Ultra硬件控制
2. 设置Start/Stop通道、阈值、甄别方向、死时间
3. 生成Histogram并可视化（对数刻度）
4. 显示Start/Stop通道计数率
5. 分析PDE、APP、Jitter（DCR由输入框提供）
6. 自动重命名并保存测试数据
"""

import sys
import os
import math
import csv
import platform
import numpy as np
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox, QMessageBox,
    QFileDialog, QGridLayout, QSplitter
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

# 配置matplotlib支持中文显示
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# 添加本地TimeTagger驱动路径

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
timetagger_base = os.path.join(current_dir, "Time Tagger", "driver")

# 1. 设置TIMETAGGER_DIR为firmware目录（用于查找.bit文件）
firmware_path = os.path.join(timetagger_base, "firmware")
if os.path.exists(firmware_path):
    os.environ['TIMETAGGER_DIR'] = firmware_path

# 2. 添加Python模块路径
timetagger_driver_path = os.path.join(timetagger_base, "python")
if os.path.exists(timetagger_driver_path) and timetagger_driver_path not in sys.path:
    sys.path.insert(0, timetagger_driver_path)
    
# 3. 添加DLL路径到PATH环境变量（根据系统架构选择x64或x86）
architecture = platform.machine().lower()
if '64' in architecture or architecture == 'amd64':
    dll_path = os.path.join(timetagger_base, "x64")
else:
    dll_path = os.path.join(timetagger_base, "x86")

if os.path.exists(dll_path):
    # 将DLL路径添加到PATH环境变量前面（确保优先找到）
    os.environ['PATH'] = dll_path + os.pathsep + os.environ.get('PATH', '')
    # 同时添加到sys.path
    if dll_path not in sys.path:
        sys.path.insert(0, dll_path)
    
    # Python 3.8+ 使用add_dll_directory来确保DLL能被找到
    if hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(dll_path)
        except Exception as e:
            print(f"  - 添加DLL目录失败: {e}")

try:
    from Swabian import TimeTagger
    TT_AVAILABLE = True
    print(f"成功加载TimeTagger库")
    print(f"  - DLL路径: {dll_path}")
    print(f"  - 固件路径: {firmware_path}")
except ImportError as e:
    TT_AVAILABLE = False
    print(f"警告: TimeTagger库加载失败，硬件功能将不可用")
    print(f"  - 错误信息: {e}")


class TDCSPADAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TDC SPAD 分析软件")
        self.setGeometry(100, 100, 1400, 900)
        
        # 硬件相关
        self.tagger = None
        self.histogram = None
        self.counter = None  # 使用Counter替代Countrate以支持1秒采样
        
        # 测量数据
        self.histogram_x = None
        self.histogram_y = None
        self.start_rate = 0
        self.stop_rate = 0
        self.is_measuring = False
        
        # 分析结果
        self.pde = 0
        self.app = 0
        self.dcr = 0
        self.jitter = 0
        
        # 初始化UI
        self.init_ui()
        
        # 计数率更新定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_countrate)
        
        # Histogram实时更新定时器
        self.histogram_timer = QTimer()
        self.histogram_timer.timeout.connect(self.update_histogram_plot)

        # 单次测量完成定时器，可在手动停止时取消
        self.measurement_timer = QTimer(self)
        self.measurement_timer.setSingleShot(True)
        self.measurement_timer.timeout.connect(self.measurement_finished)
        
    def init_ui(self):
        self.setStyleSheet(self.build_qss())

        # 主Widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # 创建左右分隔器
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        
        # ===== 左侧控制面板 =====
        left_panel = QWidget()
        left_panel.setObjectName("LeftPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # 状态栏组（连接状态 / 测试状态 / 计数率摘要）
        status_group = self.create_status_group()
        left_layout.addWidget(status_group)
        
        # 硬件配置组
        hw_group = self.create_hardware_group()
        left_layout.addWidget(hw_group)
        
        # 测试参数组
        param_group = self.create_parameter_group()
        left_layout.addWidget(param_group)
        
        # 计数率显示组
        rate_group = self.create_rate_group()
        left_layout.addWidget(rate_group)
        
        # 分析结果组
        result_group = self.create_result_group()
        left_layout.addWidget(result_group)
        
        # 数据保存配置组
        save_config_group = self.create_save_config_group()
        left_layout.addWidget(save_config_group)
        
        # 操作按钮组
        button_group = self.create_button_group()
        left_layout.addWidget(button_group)
        
        left_layout.addStretch()
        
        # 设置左侧面板固定宽度
        left_panel.setMaximumWidth(430)
        left_panel.setMinimumWidth(380)
        
        # ===== 右侧绘图区域 =====
        right_panel = QWidget()
        right_panel.setObjectName("RightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 绘图卡片（预留后续替换为PyQtGraph）
        plot_group = QGroupBox("Histogram / Time Response")
        plot_group.setProperty("class", "plotCard")
        plot_layout = QVBoxLayout(plot_group)
        plot_layout.setContentsMargins(12, 20, 12, 12)
        plot_layout.setSpacing(6)

        self.figure = Figure(facecolor='#1A1E24')
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.apply_plot_theme()
        self.figure.tight_layout(pad=0.8)

        plot_layout.addWidget(self.canvas)
        right_layout.addWidget(plot_group)
        
        # 添加到分隔器
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([420, 980])  # 右侧视觉权重 >= 65%
        
        main_layout.addWidget(splitter)

        self.set_connection_status(False)
        self.set_test_status("待机")
        self.update_status_rate_labels(0, 0)

    def build_qss(self):
        return """
QWidget {
    background-color: #161A20;
    color: #D4DCE6;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Noto Sans CJK SC";
    font-size: 16px;
}

QWidget#LeftPanel, QWidget#RightPanel {
    background-color: transparent;
}

QGroupBox {
    margin-top: 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #E6EDF5;
    font-size: 20px;
    font-weight: 600;
}

QGroupBox[class="card"] {
    border: 1px solid #2C333D;
    border-radius: 8px;
    background-color: #1B2027;
}

QGroupBox[class="plotCard"] {
    border: 1px solid #2A323E;
    border-radius: 8px;
    background-color: #1A1E24;
}

QLabel {
    color: #C9D3DF;
    font-size: 20px; 
}

QLabel#RateValue {
    color: #F2F7FC;
    font-size: 21px;
    font-weight: 700;
}

QLabel#ResultValue {
    color: #E9F2FF;
    font-size: 20px;
    font-weight: 600;
}

QLabel#StatusBadge {
    border-radius: 6px;
    border: 1px solid #36414E;
    background-color: #252C35;
    padding: 4px 8px;
    font-weight: 600;
}

QLabel#StatusBadge[state="connected"] {
    color: #95E4B1;
    border-color: #3A7250;
    background-color: #20352B;
}

QLabel#StatusBadge[state="disconnected"] {
    color: #F2A2A2;
    border-color: #734040;
    background-color: #352323;
}

QLabel#StatusBadge[state="running"] {
    color: #A4CCFF;
    border-color: #2F5B8D;
    background-color: #1D2E43;
}

QLabel#StatusBadge[state="idle"] {
    color: #D4DCE6;
    border-color: #36414E;
    background-color: #252C35;
}

QLabel#StatusRate {
    color: #DCE7F5;
    font-size: 17px;
    font-weight: 700;
}

QLineEdit, QComboBox {
    background-color: #12171D;
    border: 1px solid #374250;
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 28px;
    font-size: 13px;
    color: #E6ECF5;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #4A98FF;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QPushButton {
    background-color: #2A3340;
    border: 1px solid #3A4656;
    border-radius: 7px;
    padding: 7px 10px;
    min-height: 34px;
    font-size: 13px;
    color: #E3EAF4;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #334153;
    border-color: #4C5D72;
}

QPushButton:pressed {
    background-color: #26313E;
    border-color: #4A98FF;
}

QPushButton:disabled {
    color: #7E8A98;
    background-color: #20262E;
    border-color: #2E3640;
}

QPushButton#PrimaryButton {
    background-color: #1E5FB8;
    border: 1px solid #2D73D3;
    color: #F2F7FF;
}

QPushButton#PrimaryButton:hover {
    background-color: #2872D7;
    border-color: #4D90EA;
}

QPushButton#PrimaryButton:pressed {
    background-color: #1A57A8;
    border-color: #4A98FF;
}
"""

    def decorate_group(self, group, layout):
        group.setProperty("class", "card")
        layout.setContentsMargins(14, 16, 14, 14)
        if isinstance(layout, QGridLayout):
            layout.setHorizontalSpacing(10)
            layout.setVerticalSpacing(10)
        else:
            layout.setSpacing(10)

    def refresh_widget_style(self, widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def set_connection_status(self, is_connected):
        self.connection_status_label.setText("已连接" if is_connected else "未连接")
        self.connection_status_label.setProperty(
            "state", "connected" if is_connected else "disconnected"
        )
        self.refresh_widget_style(self.connection_status_label)

    def set_test_status(self, status_text):
        self.test_status_label.setText(status_text)
        running_states = {"连接中", "采集中", "分析中"}
        self.test_status_label.setProperty(
            "state", "running" if status_text in running_states else "idle"
        )
        self.refresh_widget_style(self.test_status_label)

    def update_status_rate_labels(self, start_rate, stop_rate):
        self.start_rate_label.setText(f"{start_rate:.0f} cps")
        self.stop_rate_label.setText(f"{stop_rate:.0f} cps")
        self.status_rate_label.setText(
            f"Start: {start_rate:.0f} cps    Stop: {stop_rate:.0f} cps"
        )

    def apply_plot_theme(self):
        self.ax.set_facecolor('#1E232A')
        self.ax.set_xlabel("Time (ps)", fontsize=18, color='#D7E0EC')
        self.ax.set_ylabel("Counts per bin", fontsize=18, color='#D7E0EC')
        self.ax.set_yscale('log')
        self.ax.grid(True, alpha=0.25, color='#3A4350', linestyle='-', linewidth=0.8)
        self.ax.tick_params(colors='#B8C3D1', which='both', labelsize=11)
        for spine in self.ax.spines.values():
            spine.set_color('#495566')

    def create_status_group(self):
        group = QGroupBox("状态栏")
        layout = QGridLayout()

        layout.addWidget(QLabel("连接状态"), 0, 0)
        self.connection_status_label = QLabel("未连接")
        self.connection_status_label.setObjectName("StatusBadge")
        layout.addWidget(self.connection_status_label, 0, 1)

        layout.addWidget(QLabel("测试状态"), 1, 0)
        self.test_status_label = QLabel("待机")
        self.test_status_label.setObjectName("StatusBadge")
        layout.addWidget(self.test_status_label, 1, 1)

        layout.addWidget(QLabel("实时计数率"), 2, 0, 1, 2)
        self.status_rate_label = QLabel("Start: 0 cps    Stop: 0 cps")
        self.status_rate_label.setObjectName("StatusRate")
        layout.addWidget(self.status_rate_label, 3, 0, 1, 2)

        self.decorate_group(group, layout)
        return group
        
    def create_hardware_group(self):
        group = QGroupBox("硬件配置")
        layout = QGridLayout()
        
        # Start通道
        layout.addWidget(QLabel("Start 通道:"), 0, 0)
        self.start_channel_combo = QComboBox()
        self.start_channel_combo.addItems([str(i) for i in range(1, 9)])
        layout.addWidget(self.start_channel_combo, 0, 1)
        
        # Stop通道
        layout.addWidget(QLabel("Stop 通道:"), 1, 0)
        self.stop_channel_combo = QComboBox()
        self.stop_channel_combo.addItems([str(i) for i in range(1, 9)])
        self.stop_channel_combo.setCurrentIndex(1)
        layout.addWidget(self.stop_channel_combo, 1, 1)
        
        # 阈值 (mV)
        layout.addWidget(QLabel("阈值 (mV):"), 2, 0)
        self.threshold_edit = QLineEdit("500")
        layout.addWidget(self.threshold_edit, 2, 1)
        
        # 甄别方向
        layout.addWidget(QLabel("甄别方向:"), 3, 0)
        self.edge_combo = QComboBox()
        self.edge_combo.addItems(["上升沿", "下降沿"])
        layout.addWidget(self.edge_combo, 3, 1)
        
        # TDC死时间 (ps)
        layout.addWidget(QLabel("TDC死时间 (ps):"), 4, 0)
        self.tdc_deadtime_edit = QLineEdit("2000")
        layout.addWidget(self.tdc_deadtime_edit, 4, 1)
        
        # 连接/断开按钮
        self.connect_btn = QPushButton("连接设备")
        self.connect_btn.clicked.connect(self.connect_device)
        layout.addWidget(self.connect_btn, 5, 0)
        
        self.disconnect_btn = QPushButton("断开连接")
        self.disconnect_btn.clicked.connect(self.disconnect_device)
        self.disconnect_btn.setEnabled(False)
        layout.addWidget(self.disconnect_btn, 5, 1)
        
        group.setLayout(layout)
        self.decorate_group(group, layout)
        return group
        
    def create_parameter_group(self):
        group = QGroupBox("测试参数")
        layout = QGridLayout()
        
        # Bin宽度 (ps)
        layout.addWidget(QLabel("Bin宽度 (ps):"), 0, 0)
        self.binwidth_edit = QLineEdit("100")
        layout.addWidget(self.binwidth_edit, 0, 1)
        
        # Bin数量
        layout.addWidget(QLabel("Bin数量:"), 1, 0)
        self.nbins_edit = QLineEdit("10000")
        layout.addWidget(self.nbins_edit, 1, 1)
        
        # 采集时间 (s)
        layout.addWidget(QLabel("采集时间 (s):"), 2, 0)
        self.acq_time_edit = QLineEdit("30")
        layout.addWidget(self.acq_time_edit, 2, 1)
        
        # 光频率 (Hz) - 用于PDE计算
        layout.addWidget(QLabel("光频率 (Hz):"), 3, 0)
        self.light_freq_edit = QLineEdit("10000")
        layout.addWidget(self.light_freq_edit, 3, 1)
        
        # SPAD死时间 (us) - 用于APP计算
        layout.addWidget(QLabel("SPAD死时间 (us):"), 4, 0)
        self.spad_deadtime_edit = QLineEdit("0.1")
        layout.addWidget(self.spad_deadtime_edit, 4, 1)

        # DCR (Hz) - 由输入框直接提供，不再从TDC数据分析
        layout.addWidget(QLabel("DCR (Hz):"), 5, 0)
        self.dcr_input_edit = QLineEdit("0")
        layout.addWidget(self.dcr_input_edit, 5, 1)
        
        group.setLayout(layout)
        self.decorate_group(group, layout)
        return group
        
    def create_rate_group(self):
        group = QGroupBox("计数率")
        layout = QGridLayout()
        
        layout.addWidget(QLabel("Start 通道:"), 0, 0)
        self.start_rate_label = QLabel("0 cps")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self.start_rate_label.setFont(font)
        self.start_rate_label.setObjectName("RateValue")
        layout.addWidget(self.start_rate_label, 0, 1)
        
        layout.addWidget(QLabel("Stop 通道:"), 1, 0)
        self.stop_rate_label = QLabel("0 cps")
        self.stop_rate_label.setFont(font)
        self.stop_rate_label.setObjectName("RateValue")
        layout.addWidget(self.stop_rate_label, 1, 1)
        
        group.setLayout(layout)
        self.decorate_group(group, layout)
        return group
        
    def create_result_group(self):
        group = QGroupBox("分析结果")
        layout = QGridLayout()
        
        font = QFont()
        font.setPointSize(13)
        
        layout.addWidget(QLabel("PDE:"), 0, 0)
        self.pde_label = QLabel("-- %")
        self.pde_label.setFont(font)
        self.pde_label.setObjectName("ResultValue")
        layout.addWidget(self.pde_label, 0, 1)
        
        layout.addWidget(QLabel("APP:"), 1, 0)
        self.app_label = QLabel("-- %")
        self.app_label.setFont(font)
        self.app_label.setObjectName("ResultValue")
        layout.addWidget(self.app_label, 1, 1)
        
        layout.addWidget(QLabel("Jitter:"), 2, 0)
        self.jitter_label = QLabel("-- ps")
        self.jitter_label.setFont(font)
        self.jitter_label.setObjectName("ResultValue")
        layout.addWidget(self.jitter_label, 2, 1)
        
        group.setLayout(layout)
        self.decorate_group(group, layout)
        return group
        
    def create_save_config_group(self):
        """数据保存配置组 (温度、偏压、门幅)"""
        group = QGroupBox("测试条件")
        layout = QGridLayout()
        
        layout.addWidget(QLabel("温度:"), 0, 0)
        self.temp_edit = QLineEdit("25")
        layout.addWidget(self.temp_edit, 0, 1)
        
        layout.addWidget(QLabel("偏压:"), 1, 0)
        self.bias_edit = QLineEdit("3.0")
        layout.addWidget(self.bias_edit, 1, 1)
        
        layout.addWidget(QLabel("门幅:"), 2, 0)
        self.gate_edit = QLineEdit("1.0")
        layout.addWidget(self.gate_edit, 2, 1)
        
        group.setLayout(layout)
        self.decorate_group(group, layout)
        return group
        
    def create_button_group(self):
        """操作按钮组"""
        group = QGroupBox("操作")
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        self.measure_btn = QPushButton("开始测量")
        self.measure_btn.setObjectName("PrimaryButton")
        self.measure_btn.clicked.connect(self.start_measurement)
        self.measure_btn.setEnabled(False)
        layout.addWidget(self.measure_btn)

        self.stop_btn = QPushButton("停止测量")
        self.stop_btn.clicked.connect(self.stop_measurement)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)
        
        self.analyze_btn = QPushButton("分析数据")
        self.analyze_btn.clicked.connect(self.analyze_data)
        self.analyze_btn.setEnabled(False)
        layout.addWidget(self.analyze_btn)
        
        self.save_btn = QPushButton("保存数据")
        self.save_btn.clicked.connect(self.save_data)
        self.save_btn.setEnabled(False)
        layout.addWidget(self.save_btn)
        
        group.setLayout(layout)
        self.decorate_group(group, layout)
        return group
        

    def connect_device(self):
        """连接Time Tagger设备"""
        if not TT_AVAILABLE:
            self.set_connection_status(False)
            self.set_test_status("硬件不可用")
            QMessageBox.warning(self, "错误", "TimeTagger库未安装")
            return
            
        try:
            self.set_test_status("连接中")
            self.tagger = TimeTagger.createTimeTagger()
            
            # 设置通道参数
            start_ch = int(self.start_channel_combo.currentText())
            stop_ch = int(self.stop_channel_combo.currentText())
            threshold_mv = float(self.threshold_edit.text())
            tdc_deadtime = int(self.tdc_deadtime_edit.text())
            
            # 设置阈值 (mV转V)
            self.tagger.setTriggerLevel(channel=start_ch, voltage=threshold_mv / 1000.0)
            self.tagger.setTriggerLevel(channel=stop_ch, voltage=threshold_mv / 1000.0)
            
            # 设置死时间
            self.tagger.setDeadtime(channel=start_ch, deadtime=tdc_deadtime)
            self.tagger.setDeadtime(channel=stop_ch, deadtime=tdc_deadtime)
            
            # 使用Counter替代Countrate，设置1秒binwidth
            self.counter = TimeTagger.Counter(
                tagger=self.tagger,
                channels=[start_ch, stop_ch],
                binwidth=int(1e12),  # 1秒 = 1e12 ps
                n_values=10  # 保留最近10个数据点
            )
            
            # 连接参数变化信号，实现动态更新
            self.threshold_edit.textChanged.connect(self.update_threshold)
            self.tdc_deadtime_edit.textChanged.connect(self.update_deadtime)
            
            # 启动计数率更新定时器 (1秒刷新)
            self.timer.start(1000)
            
            # 更新UI状态
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.set_connection_status(True)
            self.set_test_status("就绪")
            self.update_measurement_controls()
            
            QMessageBox.information(self, "成功", "设备连接成功")
            
        except Exception as e:
            self.set_connection_status(False)
            self.set_test_status("连接失败")
            QMessageBox.critical(self, "错误", f"连接设备失败:\n{str(e)}")
            
    def disconnect_device(self):
        """断开Time Tagger设备"""
        try:
            self.timer.stop()
            self.histogram_timer.stop()
            self.measurement_timer.stop()

            if self.is_measuring:
                self.stop_measurement(show_message=False)
            
            if self.histogram:
                del self.histogram
                self.histogram = None
                
            if self.counter:
                del self.counter
                self.counter = None
                
            if self.tagger:
                TimeTagger.freeTimeTagger(self.tagger)
                self.tagger = None
                
            # 更新UI状态
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.is_measuring = False
            self.update_measurement_controls()
            self.analyze_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            
            # 重置显示
            self.update_status_rate_labels(0, 0)
            self.set_connection_status(False)
            self.set_test_status("待机")
            
            QMessageBox.information(self, "成功", "设备已断开")
            
        except Exception as e:
            self.set_test_status("断开失败")
            QMessageBox.critical(self, "错误", f"断开设备失败:\n{str(e)}")
            
    def update_countrate(self):
        """更新计数率显示 (1秒采样)"""
        if self.counter:
            try:
                # 获取最新的计数数据
                data = self.counter.getData()
                if len(data) > 0 and len(data[0]) > 0:
                    # 取最后一个数据点 (1秒内的计数)
                    self.start_rate = data[0][-1]  # Start通道
                    self.stop_rate = data[1][-1] if len(data) > 1 else 0  # Stop通道
                    
                    self.update_status_rate_labels(self.start_rate, self.stop_rate)
            except:
                pass
                
    def update_threshold(self):
        """实时更新阈值设置"""
        if not self.tagger:
            return
        try:
            threshold_mv = float(self.threshold_edit.text())
            start_ch = int(self.start_channel_combo.currentText())
            stop_ch = int(self.stop_channel_combo.currentText())
            self.tagger.setTriggerLevel(channel=start_ch, voltage=threshold_mv / 1000.0)
            self.tagger.setTriggerLevel(channel=stop_ch, voltage=threshold_mv / 1000.0)
        except:
            pass
            
    def update_deadtime(self):
        """实时更新死时间设置"""
        if not self.tagger:
            return
        try:
            tdc_deadtime = int(self.tdc_deadtime_edit.text())
            start_ch = int(self.start_channel_combo.currentText())
            stop_ch = int(self.stop_channel_combo.currentText())
            self.tagger.setDeadtime(channel=start_ch, deadtime=tdc_deadtime)
            self.tagger.setDeadtime(channel=stop_ch, deadtime=tdc_deadtime)
        except:
            pass

    def update_measurement_controls(self):
        """统一更新测量相关按钮状态"""
        has_connection = self.tagger is not None
        has_histogram = (
            self.histogram_x is not None and
            self.histogram_y is not None and
            len(self.histogram_y) > 0
        )

        self.measure_btn.setEnabled(has_connection and not self.is_measuring)
        self.measure_btn.setText("开始测量")
        self.stop_btn.setEnabled(has_connection and self.is_measuring)
        self.analyze_btn.setEnabled(has_histogram and not self.is_measuring)
                
    def start_measurement(self):
        """开始测量Histogram"""
        if not self.tagger:
            self.set_test_status("未连接")
            QMessageBox.warning(self, "错误", "请先连接设备")
            return

        if self.is_measuring:
            return
            
        try:
            # 获取参数
            start_ch = int(self.start_channel_combo.currentText())
            stop_ch = int(self.stop_channel_combo.currentText())
            
            # 根据甄别方向选择通道极性
            if self.edge_combo.currentText() == "下降沿":
                start_ch = -start_ch
                stop_ch = -stop_ch
            
            binwidth = int(self.binwidth_edit.text())
            n_bins = int(self.nbins_edit.text())
            acq_time = float(self.acq_time_edit.text())

            # 新测量开始前清空旧数据与旧结果保存状态
            self.histogram_x = None
            self.histogram_y = None
            self.save_btn.setEnabled(False)

            if self.histogram:
                del self.histogram
                self.histogram = None
            
            # 创建Histogram测量
            self.histogram = TimeTagger.Histogram(
                tagger=self.tagger,
                click_channel=stop_ch,
                start_channel=start_ch,
                binwidth=binwidth,
                n_bins=n_bins
            )
            
            self.is_measuring = True
            self.update_measurement_controls()
            self.set_test_status("采集中")
            
            # 开始测量
            self.histogram.startFor(capture_duration=int(acq_time * 1e12))
            
            # 启动histogram实时更新定时器 (每100ms更新一次)
            self.histogram_timer.start(100)
            
            # 等待测量完成
            self.measurement_timer.start(int(acq_time * 1000) + 500)
            
        except Exception as e:
            self.is_measuring = False
            self.histogram_timer.stop()
            self.measurement_timer.stop()
            self.set_test_status("采集失败")
            QMessageBox.critical(self, "错误", f"开始测量失败:\n{str(e)}")
            self.update_measurement_controls()

    def stop_measurement(self, show_message=True):
        """手动停止Histogram测量"""
        if not self.histogram or not self.is_measuring:
            return

        self.measurement_finished(stopped=True, show_message=show_message)
            
    def measurement_finished(self, stopped=False, show_message=True):
        """测量完成回调"""
        if not self.histogram:
            self.is_measuring = False
            self.update_measurement_controls()
            return

        try:
            # 停止histogram实时更新定时器
            self.histogram_timer.stop()
            self.measurement_timer.stop()

            if stopped:
                self.histogram.stop()
            
            # 等待确保测量完成
            self.histogram.waitUntilFinished()

            # 获取数据
            self.histogram_x = self.histogram.getIndex()
            self.histogram_y = self.histogram.getData()

            # 绘制Histogram
            if len(self.histogram_y) > 0:
                self.plot_histogram()

            # 更新UI状态
            self.is_measuring = False
            self.update_measurement_controls()
            self.set_test_status("采集已停止" if stopped else "采集完成")

            if show_message:
                message = "测量已停止" if stopped else "测量完成"
                QMessageBox.information(self, "成功", message)
                
        except Exception as e:
            self.is_measuring = False
            self.set_test_status("采集失败")
            QMessageBox.critical(self, "错误", f"测量失败:\n{str(e)}")
            self.update_measurement_controls()
            
    def plot_histogram(self):
        """绘制Histogram（自动调整坐标轴）"""
        if self.histogram_x is None or self.histogram_y is None:
            return
            
        self.ax.clear()
        
        # 过滤掉0值以避免log刻度问题
        y_plot = np.where(self.histogram_y > 0, self.histogram_y, 1)
        
        # 绘制曲线（淡蓝色，参考TimeTagger Lab）
        self.ax.plot(self.histogram_x, y_plot, linewidth=1.2, color='#57A6FF')
        
        # 重新应用深色主题
        self.apply_plot_theme()
        
        # 自动调整坐标轴范围
        self.ax.relim()
        self.ax.autoscale_view()
        
        self.canvas.draw()
        
    def update_histogram_plot(self):
        """实时更新histogram显示（测量过程中）"""
        if self.histogram and self.is_measuring:
            try:
                # 获取当前数据
                x_data = self.histogram.getIndex()
                y_data = self.histogram.getData()
                
                if len(y_data) > 0:
                    self.ax.clear()
                    
                    # 过滤零值
                    y_plot = np.where(y_data > 0, y_data, 1)
                    
                    # 绘制
                    self.ax.plot(x_data, y_plot, linewidth=1.2, color='#57A6FF')
                    
                    # 重新应用样式
                    self.apply_plot_theme()
                    
                    # 自动调整坐标轴
                    self.ax.relim()
                    self.ax.autoscale_view()
                    
                    self.canvas.draw()
            except:
                pass
        
    def analyze_data(self):
        """分析SPAD性能参数 (参考TDC-analysis.py)"""
        if self.histogram_x is None or self.histogram_y is None:
            QMessageBox.warning(self, "错误", "没有可分析的数据")
            return
            
        try:
            self.set_test_status("分析中")
            times = self.histogram_x
            counts = self.histogram_y
            
            # 获取参数
            spad_deadtime_us = float(self.spad_deadtime_edit.text())
            light_freq = float(self.light_freq_edit.text())
            acq_time = float(self.acq_time_edit.text())
            dcr_input_hz = float(self.dcr_input_edit.text())
            if dcr_input_hz < 0:
                raise ValueError("DCR必须大于等于0")
            
            # 转换单位: us -> ps
            spad_deadtime_ps = spad_deadtime_us * 1_000_000
            
            # 1. 分析PDE和APP
            pde_app_results = self.analyze_pde_app(
                times, counts, spad_deadtime_ps, light_freq, acq_time
            )
            self.pde = pde_app_results['PDE']
            self.app = pde_app_results['APP']
            
            # 2. DCR由输入框直接提供
            self.dcr = dcr_input_hz
            
            # 3. 分析Jitter
            jitter_results = self.analyze_jitter(times, counts)
            self.jitter = jitter_results['jitter']
            
            # 更新显示
            self.pde_label.setText(f"{self.pde:.2f} %")
            self.app_label.setText(f"{self.app:.2f} %")
            self.jitter_label.setText(f"{self.jitter} ps")
            
            # 启用保存按钮
            self.save_btn.setEnabled(True)
            self.set_test_status("分析完成")
            
            QMessageBox.information(self, "成功", "分析完成")
            
        except Exception as e:
            self.set_test_status("分析失败")
            QMessageBox.critical(self, "错误", f"分析失败:\n{str(e)}")
            
    def analyze_pde_app(self, times, counts, hold_off_time_ps, PF, TT):
        """
        分析PDE和APP (参考TDC-analysis.py)
        """
        # 1. 找到最大计数及其时刻
        max_count = max(counts)
        max_index = np.argmax(counts)
        time1 = times[max_index]
        
        # 2. 从最高点向两边扩展，累加所有大于1000的计数 (PC)
        left_index = max_index
        while left_index > 0 and counts[left_index - 1] > 1000:
            left_index -= 1
        
        right_index = max_index
        while right_index < len(counts) - 1 and counts[right_index + 1] > 1000:
            right_index += 1
        
        start_index = left_index
        end_index = right_index + 1
        PC = sum(c for c in counts[start_index:end_index] if c > 1000)
        
        # 3. 计算最后20%计数的平均值 (DC)
        tail_sample_count = int(len(counts) * 0.2)
        last_counts = counts[-tail_sample_count:]
        DC = sum(last_counts) / len(last_counts) if len(last_counts) > 0 else 0
        
        # 4. 计算TC和N
        target_time = time1 + hold_off_time_ps
        
        target_index = None
        for i, time_val in enumerate(times):
            if time_val >= target_time:
                target_index = i
                break
        
        if target_index is None:
            target_index = len(times)
        
        TC = sum(counts[target_index:])
        N = len(counts[target_index:])
        
        # 5. 计算PDE和APP
        try:
            pde_ratio = PC / TT / PF
            if pde_ratio < 1:
                PDE = -math.log(1 - pde_ratio) * 100
            else:
                PDE = float('inf')
        except (ValueError, ZeroDivisionError):
            PDE = 0
        
        try:
            APP = (TC - DC * N) / PC * 100 if PC != 0 else 0
        except ZeroDivisionError:
            APP = 0
        
        return {
            'PDE': PDE,
            'APP': APP,
            'PC': PC,
            'DC': DC,
            'TC': TC,
            'N': N
        }
        
    def analyze_jitter(self, times, counts):
        """按主峰半峰宽(FWHM)分析Jitter"""
        if len(times) == 0 or len(counts) == 0:
            return {
                'jitter': 0,
                'jitter_ps': 0
            }

        counts_array = np.asarray(counts, dtype=float)
        times_array = np.asarray(times, dtype=float)

        max_index = int(np.argmax(counts_array))
        peak_value = counts_array[max_index]
        if peak_value <= 0:
            return {
                'jitter': 0,
                'jitter_ps': 0
            }

        tail_sample_count = max(1, int(len(counts_array) * 0.2))
        baseline = float(np.mean(counts_array[-tail_sample_count:]))
        half_max = baseline + (peak_value - baseline) / 2.0

        left_index = max_index
        while left_index > 0 and counts_array[left_index] >= half_max:
            left_index -= 1

        right_index = max_index
        while right_index < len(counts_array) - 1 and counts_array[right_index] >= half_max:
            right_index += 1

        def interpolate_crossing(x0, y0, x1, y1, target):
            if y1 == y0:
                return x0
            return x0 + (target - y0) * (x1 - x0) / (y1 - y0)

        if left_index == 0 and counts_array[left_index] >= half_max:
            left_time = times_array[left_index]
        elif left_index == max_index:
            left_time = times_array[max_index]
        else:
            left_time = interpolate_crossing(
                times_array[left_index],
                counts_array[left_index],
                times_array[left_index + 1],
                counts_array[left_index + 1],
                half_max
            )

        if right_index == len(counts_array) - 1 and counts_array[right_index] >= half_max:
            right_time = times_array[right_index]
        elif right_index == max_index:
            right_time = times_array[max_index]
        else:
            right_time = interpolate_crossing(
                times_array[right_index - 1],
                counts_array[right_index - 1],
                times_array[right_index],
                counts_array[right_index],
                half_max
            )

        jitter = int(round(max(0.0, right_time - left_time)))
        
        return {
            'jitter': jitter,
            'jitter_ps': jitter
        }
        
    def save_data(self):
        """保存数据到CSV文件，自动重命名"""
        if self.histogram_x is None or self.histogram_y is None:
            QMessageBox.warning(self, "错误", "没有可保存的数据")
            return
            
        try:
            # 获取用户输入参数
            temp = self.temp_edit.text()
            bias = self.bias_edit.text()
            gate = self.gate_edit.text()
            
            # 格式化文件名
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"Temp{temp}-Bias{bias}-Gate{gate}-DCR{self.dcr:.0f}-PDE{self.pde:.2f}-APP{self.app:.2f}-{date_str}.csv"
            
            # 选择保存路径
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存数据",
                filename,
                "CSV文件 (*.csv)"
            )
            
            if not save_path:
                return
                
            # 元数据按列写入，避免值中出现换行，并保持PDE/APP统一为 key=value 格式
            metadata_row = [
                f"BinWidth={self.binwidth_edit.text()}ps",
                f"NumBins={self.nbins_edit.text()}",
                f"AcqTime={self.acq_time_edit.text()}s",
                f"LightFreq={self.light_freq_edit.text()}Hz",
                f"SPADDeadtime={self.spad_deadtime_edit.text()}us",
                f"Temp={temp}",
                f"Bias={bias}",
                f"Gate={gate}",
                f"PDE={self.pde:.2f}%",
                f"APP={self.app:.2f}%",
                f"DCR={self.dcr:.2f}Hz",
                f"Jitter={self.jitter}ps",
            ]

            # 写入文件
            with open(save_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(metadata_row)
                writer.writerow(['Time(ps)', 'Counts'])
                for time_ps, count in zip(self.histogram_x, self.histogram_y):
                    writer.writerow([time_ps, count])
                
            QMessageBox.information(self, "成功", f"数据已保存到:\n{save_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败:\n{str(e)}")


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 11))
    window = TDCSPADAnalyzer()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
