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
        # 新增：下一张卡类型提示（大号字，醒目）
        self.next_card_label = QLabel("请加载工单...")
        self.next_card_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3; padding: 4px;")
        # 新增：配额分布摘要
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-size: 12px; color: #666;")
        self.summary_label.setWordWrap(True)
        status_layout.addWidget(self.device_status_label)
        status_layout.addWidget(self.network_status_label)
        status_layout.addWidget(self.quota_label)
        status_layout.addWidget(self.next_card_label)
        status_layout.addWidget(self.summary_label)
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
        self.refresh_button = QPushButton("刷新状态")
        self.manage_button = QPushButton("卡片管理")
        self.switch_order_button = QPushButton("切换工单")
        self.refresh_button.setToolTip("从服务器重新拉取工单状态、配额、下一张卡类型")
        self.manage_button.setToolTip("查询/取消已烧录的卡片（用于烧错卡后重烧）")
        self.switch_order_button.setToolTip("返回工单列表，选择其他工单")
        self.start_button.clicked.connect(self.start_burning)
        self.stop_button.clicked.connect(self.stop_burning)
        self.refresh_button.clicked.connect(self.manual_refresh)
        self.manage_button.clicked.connect(self.open_card_manager)
        self.switch_order_button.clicked.connect(self.switch_order)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.manage_button)
        button_layout.addWidget(self.switch_order_button)
        
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
        # 打印调用栈，看是谁触发的 stop_burning
        import traceback
        print("=" * 60)
        print("[MAIN] stop_burning() 被调用，调用栈：")
        traceback.print_stack()
        print("=" * 60)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("已停止")
        self.nfc_reader.stop()

    def manual_refresh(self):
        """用户手动点"刷新状态"：重新拉取工单 + 配额 + 下一张卡类型。"""
        self.set_status("正在刷新工单状态...")
        try:
            self.refresh_task_status()
            # refresh_task_status 只在 has_limit 时才调 update_quota_display
            # 如果当前没工单，load_task 会重新走完整加载流程
            if not self.current_task or not self.current_task.get('has_task', True):
                self.load_task()
            self.set_status("工单状态已刷新")
        except Exception as e:
            self.set_status(f"刷新失败: {e}", is_error=True)

    def switch_order(self):
        """停止当前烧录并返回工单选择页面。"""
        if self.nfc_reader and getattr(self.nfc_reader, 'running', False):
            resp = QMessageBox.question(
                self, '切换工单', '当前正在烧录，确定停止并返回工单列表吗？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            self.nfc_reader.stop()
            if self.nfc_reader.isRunning():
                self.nfc_reader.wait(3000)
        cb = getattr(self, 'back_to_orders_requested', None)
        if callable(cb):
            cb()
        else:
            self.close()

    def open_card_manager(self):
        """打开卡片管理窗口（查询/取消已烧录卡片）"""
        # 检查烧录是否真正停止了
        # 用 self.nfc_reader.running（我们自己维护的标志位）判断，而不是 QThread.isRunning()
        # 因为 QThread 即便 stop() 调用后可能还需要 1-2 秒才完全退出
        if self.nfc_reader and getattr(self.nfc_reader, 'running', False):
            QMessageBox.warning(
                self, '请先停止烧录',
                '请先点「停止烧录」按钮，再打开卡片管理。'
            )
            return

        # 如果线程还在运行但标志位已关，强制等一下
        if self.nfc_reader and self.nfc_reader.isRunning():
            print("[MAIN] 等待烧录线程完全退出...")
            self.nfc_reader.wait(3000)

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

            # 保存记录到服务器（注意 create_burning_record 现在返回 dict 不是 bool）
            api_result = None
            try:
                api_result = self.api_client.create_burning_record(record_data)
            except Exception as e:
                api_result = {'ok': False, 'error': f'调用异常: {e}',
                              'permanent': False, 'queued_offline': False,
                              'queued_for_retry': False}

            # 后端确认入库 = 真正的成功；物理写入但后端拒收时不能算 success
            backend_ok = bool(api_result and api_result.get('ok'))
            backend_err = (api_result or {}).get('error') or ''
            backend_permanent = bool(api_result and api_result.get('permanent'))

            effective_success = success and backend_ok

            # 永久错误：物理卡已写但 DB 没记录 —— 弹明显警告，提示用户处理
            if success and not backend_ok and backend_permanent:
                QMessageBox.warning(
                    self,
                    "卡片已写但工单已满 / 不可入库",
                    f"物理 NFC 已写入：{nfc_id}\n用户ID：{user_id}\n\n"
                    f"但后端拒收：{backend_err}\n\n"
                    f"⚠️ 这张物理卡处于不一致状态。\n"
                    f"建议：\n"
                    f"  • 报废该卡 或\n"
                    f"  • 联系管理员重置工单 / 调整配额后通过『重烧』恢复",
                )
            elif success and not backend_ok and not backend_permanent:
                # 临时错误：已经放入离线队列，下次会重试
                self.status_label.setText(f"警告：记录暂存离线（{backend_err}），将在下次重试")

            # 如果真正成功，更新本地配额显示
            if effective_success and "max_cards" in self.current_task and "burned_cards" in self.current_task:
                max_cards = self.current_task.get("max_cards", 0)
                if max_cards > 0:
                    # 先更新本地计数，确保即时反馈
                    burned_cards = self.current_task.get("burned_cards", 0) + 1
                    remaining = max(0, max_cards - burned_cards)
                    self.current_task["burned_cards"] = burned_cards
                    self.current_task["remaining"] = remaining
                    self.update_quota_display(max_cards, burned_cards, remaining)

            # 真正成功才刷新任务状态
            if effective_success:
                QTimer.singleShot(1000, self.refresh_task_status)

            # 更新界面显示
            if effective_success:
                self.success_count += 1
                self.success_lcd.display(self.success_count)
                self.success_sound.play()
                status_text = f"烧录成功，用户ID: {user_id}" if user_id else "烧录成功，请移除卡片"
                self.status_label.setText(status_text)
            else:
                # 物理失败 或 后端拒收 都算失败
                self.fail_count += 1
                self.fail_lcd.display(self.fail_count)
                self.fail_sound.play()
                if not success:
                    self.status_label.setText("烧录失败，请移除卡片后重试")
                elif backend_permanent:
                    self.status_label.setText(f"卡已写但工单不收：{backend_err}")
                else:
                    self.status_label.setText(f"已暂存离线：{backend_err}")

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

        # 更新"下一张卡"提示
        if hasattr(self, 'current_task') and self.current_task:
            self.update_next_card_hint(self.current_task)

    def update_next_card_hint(self, task: dict):
        """根据 task_status 更新下一张卡类型提示 + 配额摘要"""
        CARD_LABEL = {
            'content': '📀 内容卡',
            'recording': '🎙️ 录音卡',
            'family': '👨‍👩‍👧 家庭卡',
        }
        CARD_COLOR = {
            'content': '#1976D2',    # 蓝色
            'recording': '#388E3C',  # 绿色
            'family': '#F57C00',     # 橙色
        }

        next_type = task.get('next_card_type') or task.get('card_type') or 'content'
        next_group = task.get('next_group_id')
        remaining = task.get('remaining', 0)

        if remaining <= 0:
            self.next_card_label.setText("✓ 工单已完成")
            self.next_card_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #4CAF50; padding: 4px;")
        else:
            label_text = f"下一张: {CARD_LABEL.get(next_type, next_type)}"
            if next_type == 'content' and next_group:
                label_text += f"  (内容组: {next_group[:8]}...)"
            self.next_card_label.setText(label_text)
            color = CARD_COLOR.get(next_type, '#2196F3')
            self.next_card_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color}; padding: 4px;")

        # 配额分布摘要：按 (card_type, group_id) 合并，避免被拆成 N 条单位为 1 的条目刷屏
        summary = task.get('contents_summary') or []
        if summary:
            merged = {}  # key -> {card_type, group_id, quantity, burned}
            order_keys = []
            for item in summary:
                ct = item.get('card_type', '?')
                gid = item.get('group_id') if ct == 'content' else None
                key = (ct, gid)
                if key not in merged:
                    merged[key] = {'card_type': ct, 'group_id': gid, 'quantity': 0, 'burned': 0}
                    order_keys.append(key)
                merged[key]['quantity'] += item.get('quantity', 0)
                merged[key]['burned'] += item.get('burned', 0)

            parts = []
            for key in order_keys:
                entry = merged[key]
                ct = entry['card_type']
                label = CARD_LABEL.get(ct, ct).replace('📀', '').replace('🎙️', '').replace('👨‍👩‍👧', '').strip()
                # 多个不同内容组时在标签后加短 group id 区分
                if ct == 'content' and entry['group_id']:
                    same_type_count = sum(1 for k in merged if k[0] == 'content')
                    if same_type_count > 1:
                        label += f"({entry['group_id'][:6]})"
                parts.append(f"{label} {entry['burned']}/{entry['quantity']}")
            self.summary_label.setText("配额分布: " + " | ".join(parts))
        else:
            self.summary_label.setText("")
            
    def refresh_task_status(self):
        """刷新任务状态，检查限制"""
        try:
            task_status = self.api_client.get_task_status()
            if not task_status or not task_status.get("has_task", False):
                print("[REFRESH] 后端返回无工单")
                return

            current_id = self.current_task.get("id") if self.current_task else None
            returned_id = task_status.get("id")
            burned = task_status.get("burned_cards", 0)
            remaining = task_status.get("remaining", 0)
            next_type = task_status.get("next_card_type")
            new_url = task_status.get("url", "")
            old_url = self.nfc_reader.current_url or ""

            print(f"[REFRESH] current_id={current_id}, returned_id={returned_id}, burned={burned}, remaining={remaining}, next={next_type}")
            if new_url and new_url != old_url:
                print(f"[REFRESH] URL 变化 {old_url} -> {new_url}，更新到 NFC reader")
                self.nfc_reader.set_url(new_url)

            if current_id and returned_id and current_id != returned_id:
                print(f"[REFRESH] 工单 id 变化 {current_id}->{returned_id}，触发停止")
                self.set_status(f"工单 #{current_id} 已完成。请点「停止烧录」→ 再点「开始烧录」领取下一个工单")
                self.status_label.setStyleSheet("color: orange; font-weight: bold")
                self.stop_burning()
                return

            if not task_status.get("has_limit", False):
                self.current_task = task_status
                return

            max_cards = task_status.get("max_cards", 0)
            burned_cards = task_status.get("burned_cards", 0)

            self.current_task = task_status
            self.update_quota_display(max_cards, burned_cards, remaining)

            if remaining <= 0:
                print(f"[REFRESH] 剩余为 0，触发停止")
                self.set_status(f"工单 #{returned_id} 已完成（{burned_cards}/{max_cards}），烧录停止")
                self.status_label.setStyleSheet("color: green; font-weight: bold")
                self.stop_burning()
            else:
                print(f"[REFRESH] 继续烧录（剩余 {remaining}），下一张: {next_type}")
        except Exception as e:
            print(f"刷新任务状态失败: {e}") 