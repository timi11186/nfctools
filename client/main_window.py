from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QLabel, QPushButton, QGroupBox, QLCDNumber, QMessageBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl
from pathlib import Path
from .api_client import APIClient
from .nfc_reader import NFCReader
from datetime import datetime
import time

class MainWindow(QMainWindow):
    def __init__(self, api_client: APIClient):
        super().__init__()
        self.api_client = api_client
        self.current_task = None
        self.success_count = 0
        self.fail_count = 0
        
        # 初始化NFC读写器
        self.nfc_reader = NFCReader()
        self.nfc_reader.status_changed.connect(self.update_device_status)
        self.nfc_reader.burning_complete.connect(self.handle_burning_complete)
        self.nfc_reader.device_connected.connect(self.update_device_connection)
        
        # 初始化声音效果
        self.success_sound = QSoundEffect()
        self.success_sound.setSource(QUrl.fromLocalFile(str(Path("./assets/success.wav"))))
        self.fail_sound = QSoundEffect()
        self.fail_sound.setSource(QUrl.fromLocalFile(str(Path("./assets/fail.wav"))))
        
        self.init_ui()
        self.init_timers()
        self.load_task()
        
    def init_ui(self):
        self.setWindowTitle("NFC烧录系统")
        self.setMinimumSize(600, 400)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 设备状态区域
        status_group = QGroupBox("设备状态")
        status_layout = QVBoxLayout()
        self.device_status_label = QLabel("未连接")
        self.network_status_label = QLabel("网络状态: 检查中...")
        self.quota_label = QLabel("卡片配额: 未加载")
        status_layout.addWidget(self.device_status_label)
        status_layout.addWidget(self.network_status_label)
        status_layout.addWidget(self.quota_label)
        status_group.setLayout(status_layout)
        
        # 操作区域
        operation_group = QGroupBox("操作区")
        operation_layout = QVBoxLayout()
        
        # 状态显示
        self.status_label = QLabel("等待开始...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("开始烧录")
        self.stop_button = QPushButton("停止烧录")
        self.manage_button = QPushButton("卡片管理")
        self.manage_button.setToolTip("查询/取消已烧录的卡片（用于烧错卡后重烧）")
        self.start_button.clicked.connect(self.start_burning)
        self.stop_button.clicked.connect(self.stop_burning)
        self.manage_button.clicked.connect(self.open_card_manager)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.manage_button)
        
        operation_layout.addWidget(self.status_label)
        operation_layout.addLayout(button_layout)
        operation_group.setLayout(operation_layout)
        
        # 计数显示区域
        counter_group = QGroupBox("计数显示")
        counter_layout = QHBoxLayout()
        
        # 成功计数
        success_layout = QVBoxLayout()
        success_layout.addWidget(QLabel("成功数量"))
        self.success_lcd = QLCDNumber()
        self.success_lcd.setDigitCount(4)
        self.success_lcd.display(0)
        success_layout.addWidget(self.success_lcd)
        
        # 失败计数
        fail_layout = QVBoxLayout()
        fail_layout.addWidget(QLabel("失败数量"))
        self.fail_lcd = QLCDNumber()
        self.fail_lcd.setDigitCount(4)
        self.fail_lcd.display(0)
        fail_layout.addWidget(self.fail_lcd)
        
        counter_layout.addLayout(success_layout)
        counter_layout.addLayout(fail_layout)
        counter_group.setLayout(counter_layout)
        
        # 添加所有组件到主布局
        layout.addWidget(status_group)
        layout.addWidget(operation_group)
        layout.addWidget(counter_group)
        
    def init_timers(self):
        # 网络状态检查定时器
        self.network_timer = QTimer()
        self.network_timer.timeout.connect(self.check_network)
        self.network_timer.start(5000)  # 每5秒检查一次
        
        # 离线数据同步定时器
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.sync_offline_data)
        self.sync_timer.start(30000)  # 每30秒尝试同步一次
        
    def check_network(self):
        task = self.api_client.get_current_task()
        if task:
            self.network_status_label.setText("网络状态: 在线")
            self.current_task = task
        else:
            self.network_status_label.setText("网络状态: 离线")
            
    def sync_offline_data(self):
        if self.api_client.sync_offline_records():
            print("离线数据同步成功")
            
    def start_burning(self):
        if not self.current_task:
            self.status_label.setText("错误: 未获取到烧录任务")
            return
            
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("烧录进行中...")
        self.nfc_reader.start()
        
    def stop_burning(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("已停止")
        self.nfc_reader.stop()

    def open_card_manager(self):
        """打开卡片管理窗口（查询/取消已烧录卡片）"""
        # 烧录中禁止打开管理窗口，避免读卡器冲突
        if self.nfc_reader and getattr(self.nfc_reader, 'isRunning', lambda: False)():
            QMessageBox.warning(
                self, '请先停止烧录',
                '烧录工作线程占用读卡器，请先点「停止烧录」再打开卡片管理。'
            )
            return

        # 延迟 import 避免循环依赖
        from .card_manager_window import CardManagerWindow
        dlg = CardManagerWindow(
            api_client=self.api_client,
            current_order_id=self.current_task.get('id') if self.current_task else None,
            parent=self,
        )
        dlg.exec()
        # 关闭管理窗口后刷新工单状态（取消操作可能改变 bound_count）
        self.load_task()


    def update_device_status(self, status: str):
        """更新设备状态显示"""
        # 添加时间戳
        timestamp = datetime.now().strftime("%H:%M:%S")
        status_text = f"[{timestamp}] {status}"
        
        # 更新状态标签
        self.status_label.setText(status_text)
        
        # 根据状态类型设置颜色
        if "成功" in status:
            self.status_label.setStyleSheet("color: green")
        elif "失败" in status or "错误" in status:
            self.status_label.setStyleSheet("color: red")
        else:
            self.status_label.setStyleSheet("color: black")
        
    def handle_burning_complete(self, success: bool, user_id: str = "", nfc_id: str = ""):
        """处理烧录完成事件"""
        try:
            # 调试日志
            print(f"烧录完成事件触发: success={success}, user_id={user_id}, nfc_id={nfc_id}")
            
            # 确保有当前任务
            if not hasattr(self, 'current_task') or not self.current_task:
                self.status_label.setText("错误：无当前任务")
                return
                
            # 添加防重复处理
            if not hasattr(self, 'last_nfc_id') or not hasattr(self, 'last_user_id'):
                self.last_nfc_id = ""
                self.last_user_id = ""
                self.last_success_time = 0
                
            # 如果NFC ID不为空且与上次相同，且时间间隔小于3秒，认为是重复事件
            current_time = time.time()
            if nfc_id and nfc_id == self.last_nfc_id and current_time - getattr(self, 'last_success_time', 0) < 3:
                print(f"检测到重复事件，已忽略。上次NFC ID: {self.last_nfc_id}, 当前NFC ID: {nfc_id}, 时间差: {current_time - self.last_success_time}秒")
                self.status_label.setText(f"重复事件，已忽略")
                return
                
            print(f"事件被接受处理，上次NFC ID: {getattr(self, 'last_nfc_id', 'None')}, 当前NFC ID: {nfc_id}")
            
            # 更新最后处理的卡片信息
            self.last_nfc_id = nfc_id
            self.last_user_id = user_id
            self.last_success_time = current_time

            # 创建烧录记录
            record_data = {
                'task_id': self.current_task['id'],
                'status': success,
                'retry_count': self.nfc_reader.retry_count if hasattr(self.nfc_reader, 'retry_count') else 0,
                'user_id': user_id,
                'nfc_id': nfc_id
            }

            # 保存记录到服务器
            try:
                response = self.api_client.create_burning_record(record_data)
                if not response:
                    self.status_label.setText("警告：记录保存失败")
            except Exception as e:
                self.status_label.setText(f"警告：记录保存失败 - {str(e)}")
                
            # 如果烧录成功，更新本地配额显示
            if success and "max_cards" in self.current_task and "burned_cards" in self.current_task:
                max_cards = self.current_task.get("max_cards", 0)
                if max_cards > 0:
                    # 先更新本地计数，确保即时反馈
                    burned_cards = self.current_task.get("burned_cards", 0) + 1
                    remaining = max(0, max_cards - burned_cards)
                    self.current_task["burned_cards"] = burned_cards
                    self.current_task["remaining"] = remaining
                    self.update_quota_display(max_cards, burned_cards, remaining)
                
            # 如果烧录成功，刷新任务状态以获取最新的限制信息
            if success:
                # 延迟一秒再刷新，确保服务器已处理
                QTimer.singleShot(1000, self.refresh_task_status)
                
            # 更新界面显示
            if success:
                self.success_count += 1
                self.success_lcd.display(self.success_count)
                self.success_sound.play()
                status_text = f"烧录成功，用户ID: {user_id}" if user_id else "烧录成功，请移除卡片"
                self.status_label.setText(status_text)
            else:
                self.fail_count += 1
                self.fail_lcd.display(self.fail_count)
                self.fail_sound.play()
                self.status_label.setText("烧录失败，请移除卡片后重试")

        except Exception as e:
            self.status_label.setText(f"错误：{str(e)}")
        
    def update_device_connection(self, connected: bool):
        """更新设备连接状态"""
        if connected:
            self.device_status_label.setText("读卡器已连接")
            self.device_status_label.setStyleSheet("color: green")
            self.start_button.setEnabled(True)
        else:
            self.device_status_label.setText("读卡器未连接")
            self.device_status_label.setStyleSheet("color: red")
            self.start_button.setEnabled(False)
            
    def set_status(self, text: str, is_error: bool = False):
        """更新状态文本"""
        self.status_label.setText(text)
        if is_error:
            self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setStyleSheet("")
            
    def closeEvent(self, event):
        """窗口关闭事件"""
        self.nfc_reader.stop()
        event.accept()

    def load_task(self):
        """加载烧录任务"""
        try:
            # 优先尝试获取更详细的任务状态
            task_status = self.api_client.get_task_status()
            
            if task_status and task_status.get("has_task", False):
                self.current_task = task_status
                task_url = task_status.get("url", "")
                self.nfc_reader.set_url(task_url)
                
                # 显示卡片限制信息
                if task_status.get("has_limit", False):
                    max_cards = task_status.get("max_cards", 0)
                    burned_cards = task_status.get("burned_cards", 0)
                    remaining = task_status.get("remaining", 0)
                    
                    # 更新配额标签
                    self.update_quota_display(max_cards, burned_cards, remaining)
                    
                    if remaining <= 0:
                        self.status_label.setText(f"警告：已达到烧录限制({burned_cards}/{max_cards})")
                        self.status_label.setStyleSheet("color: red; font-weight: bold")
                        self.start_button.setEnabled(False)
                    else:
                        self.set_status(f"已加载任务: {task_url}（剩余配额: {remaining}）")
                        self.start_button.setEnabled(True)
                else:
                    self.quota_label.setText("卡片配额: 无限制")
                    self.set_status(f"已加载任务: {task_url}")
                    self.start_button.setEnabled(True)
                
                return True
            
            # 降级使用旧方法
            task = self.api_client.get_current_task()
            if task:
                self.current_task = task
                self.nfc_reader.set_url(task["url"])
                self.quota_label.setText("卡片配额: 未知")
                self.set_status(f"已加载任务: {task['url']}")
                self.start_button.setEnabled(True)
                return True
            else:
                self.quota_label.setText("卡片配额: 无任务")
                self.set_status("当前没有烧录任务，请联系管理员")
                self.start_button.setEnabled(False)
                return False
                
        except Exception as e:
            self.quota_label.setText("卡片配额: 加载失败")
            self.set_status(f"加载任务失败: {str(e)}")
            self.start_button.setEnabled(False)
            return False
            
    def update_quota_display(self, max_cards, burned_cards, remaining):
        """更新配额显示"""
        if max_cards > 0:
            # 显示进度百分比
            progress = (burned_cards / max_cards) * 100
            if remaining <= 0:
                self.quota_label.setText(f"卡片配额: {burned_cards}/{max_cards} (已用完)")
                self.quota_label.setStyleSheet("color: red; font-weight: bold;")
            elif remaining <= max_cards * 0.1:  # 小于10%时显示警告
                self.quota_label.setText(f"卡片配额: {burned_cards}/{max_cards} (剩余: {remaining}, {progress:.1f}%)")
                self.quota_label.setStyleSheet("color: orange; font-weight: bold;")
            else:
                self.quota_label.setText(f"卡片配额: {burned_cards}/{max_cards} (剩余: {remaining}, {progress:.1f}%)")
                self.quota_label.setStyleSheet("color: green;")
        else:
            self.quota_label.setText("卡片配额: 无限制")
            self.quota_label.setStyleSheet("")
            
    def refresh_task_status(self):
        """刷新任务状态，检查限制"""
        try:
            task_status = self.api_client.get_task_status()
            
            if task_status and task_status.get("has_task", False) and task_status.get("has_limit", False):
                max_cards = task_status.get("max_cards", 0)
                burned_cards = task_status.get("burned_cards", 0)
                remaining = task_status.get("remaining", 0)
                
                self.current_task = task_status
                
                # 更新配额显示
                self.update_quota_display(max_cards, burned_cards, remaining)
                
                if remaining <= 0:
                    self.set_status(f"已达到烧录限制({burned_cards}/{max_cards})，请联系管理员")
                    self.status_label.setStyleSheet("color: red; font-weight: bold")
                    self.start_button.setEnabled(False)
                    self.stop_burning()
        except Exception as e:
            print(f"刷新任务状态失败: {e}") 