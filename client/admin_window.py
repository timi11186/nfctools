from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QLabel, QPushButton, QGroupBox, QTableWidget, 
                           QTableWidgetItem, QDialog, QLineEdit, QMessageBox,
                           QDateEdit, QTabWidget, QHeaderView, QSpinBox, QTextEdit,
                           QCheckBox)
from PyQt6.QtCore import Qt, QDate
from .api_client import APIClient
import datetime

class AddEmployeeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("添加员工")
        layout = QVBoxLayout()
        
        # 用户名输入
        username_layout = QHBoxLayout()
        username_label = QLabel("用户名:")
        self.username_input = QLineEdit()
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        
        # 密码输入
        password_layout = QHBoxLayout()
        password_label = QLabel("密码:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        
        # 确认按钮
        button_layout = QHBoxLayout()
        ok_button = QPushButton("确定")
        cancel_button = QPushButton("取消")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(username_layout)
        layout.addLayout(password_layout)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
    def get_data(self):
        return {
            "username": self.username_input.text(),
            "password": self.password_input.text()
        }

class AdminWindow(QMainWindow):
    def __init__(self, api_client: APIClient):
        super().__init__()
        self.api_client = api_client
        self.init_ui()
        self.load_data()
        
    def init_ui(self):
        self.setWindowTitle("NFC烧录系统 - 管理后台")
        self.setMinimumSize(1000, 600)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        layout = QVBoxLayout(central_widget)
        
        # 创建标签页
        tab_widget = QTabWidget()
        
        # 员工管理标签页
        employee_tab = QWidget()
        tab_widget.addTab(employee_tab, "员工管理")
        self.init_employee_tab(employee_tab)
        
        # 烧录任务标签页
        self.task_tab = QWidget()
        tab_widget.addTab(self.task_tab, "烧录任务")
        self.init_task_tab()
        
        # 数据统计标签页
        stats_tab = QWidget()
        tab_widget.addTab(stats_tab, "数据统计")
        self.init_stats_tab(stats_tab)
        
        layout.addWidget(tab_widget)
        
    def init_employee_tab(self, tab):
        layout = QVBoxLayout(tab)
        
        # 工具栏
        toolbar = QHBoxLayout()
        add_button = QPushButton("添加员工")
        add_button.clicked.connect(self.add_employee)
        toolbar.addWidget(add_button)
        toolbar.addStretch()
        
        # 员工列表
        self.employee_table = QTableWidget()
        self.employee_table.setColumnCount(5)  # 增加一列用于显示密码
        self.employee_table.setHorizontalHeaderLabels(["ID", "用户名", "初始密码", "状态", "操作"])
        
        layout.addLayout(toolbar)
        layout.addWidget(self.employee_table)
        
    def init_task_tab(self):
        """初始化任务管理标签页"""
        layout = QVBoxLayout()
        
        # 创建任务分组
        create_group = QGroupBox("创建任务")
        create_layout = QVBoxLayout()
        
        # URL输入
        url_layout = QHBoxLayout()
        url_label = QLabel("烧录URL:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入需要烧录的URL")
        # 加载默认URL
        self.load_default_url()
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        
        # 保存为默认URL选项
        default_url_layout = QHBoxLayout()
        self.save_default_url_checkbox = QCheckBox("保存为默认URL")
        self.save_default_url_checkbox.setChecked(True)
        default_url_layout.addWidget(self.save_default_url_checkbox)
        default_url_layout.addStretch()
        
        # 卡片限制输入
        limit_layout = QHBoxLayout()
        limit_label = QLabel("卡片数量限制:")
        self.limit_input = QSpinBox()
        self.limit_input.setRange(0, 9999)  # 0表示无限制
        self.limit_input.setValue(0)
        self.limit_input.setSpecialValueText("无限制")  # 当值为0时显示"无限制"
        limit_layout.addWidget(limit_label)
        limit_layout.addWidget(self.limit_input)
        
        # 设置任务按钮
        self.set_task_btn = QPushButton("设置烧录任务")
        self.set_task_btn.clicked.connect(self.set_task)
        
        # 添加组件到创建布局
        create_layout.addLayout(url_layout)
        create_layout.addLayout(default_url_layout)
        create_layout.addLayout(limit_layout)
        create_layout.addWidget(self.set_task_btn)
        create_group.setLayout(create_layout)
        
        # 任务列表分组
        task_list_group = QGroupBox("任务列表")
        task_list_layout = QVBoxLayout()
        
        # 任务表格
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(6)
        self.task_table.setHorizontalHeaderLabels(["ID", "URL", "状态", "已烧录/限制", "创建时间", "操作"])
        self.task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新任务列表")
        refresh_btn.clicked.connect(self.load_task_list)
        
        task_list_layout.addWidget(self.task_table)
        task_list_layout.addWidget(refresh_btn)
        task_list_group.setLayout(task_list_layout)
        
        # 添加组件到主布局
        layout.addWidget(create_group)
        layout.addWidget(task_list_group)
        
        self.task_tab.setLayout(layout)
        
        # 加载当前任务和任务列表
        self.load_current_task()
        self.load_task_list()
    
    def set_task(self):
        """设置烧录任务"""
        url = self.url_input.text().strip()
        max_cards = self.limit_input.value()
        
        if not url:
            QMessageBox.warning(self, "错误", "URL不能为空")
            return
            
        try:
            # 检查URL格式
            if not url.startswith("http://") and not url.startswith("https://"):
                if QMessageBox.question(
                    self, 
                    "URL格式", 
                    "URL不是以http://或https://开头的，是否添加https://前缀？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                ) == QMessageBox.StandardButton.Yes:
                    url = "https://" + url
                    self.url_input.setText(url)
            
            # 保存默认URL
            if self.save_default_url_checkbox.isChecked():
                self.save_default_url(url)
            
            # 准备任务数据
            task_data = {
                "url": url,
                "max_cards": max_cards
            }
            
            # 发送请求创建任务
            result = self.api_client.create_task(task_data)
            
            if result:
                QMessageBox.information(self, "成功", "烧录任务设置成功")
                self.load_task_list()
            else:
                QMessageBox.warning(self, "错误", "设置任务失败")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"设置任务时发生异常: {str(e)}")
    
    def load_current_task(self):
        """加载当前任务信息(保留兼容性)"""
        self.load_task_list()  # 直接刷新任务列表
    
    def init_stats_tab(self, tab):
        layout = QVBoxLayout(tab)
        
        # 日期选择
        date_layout = QHBoxLayout()
        self.date_picker = QDateEdit()
        self.date_picker.setDate(QDate.currentDate())
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh_stats)
        date_layout.addWidget(QLabel("选择日期:"))
        date_layout.addWidget(self.date_picker)
        date_layout.addWidget(refresh_button)
        date_layout.addStretch()
        
        # 统计表格
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(4)
        self.stats_table.setHorizontalHeaderLabels(["员工", "总数量", "成功", "失败"])
        
        layout.addLayout(date_layout)
        layout.addWidget(self.stats_table)
        
    def load_data(self):
        """加载初始数据"""
        self.refresh_employee_list()
        self.refresh_current_task()
        self.refresh_stats()
        
    def add_employee(self):
        dialog = AddEmployeeDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                self.api_client.create_employee(data)
                self.refresh_employee_list()
                QMessageBox.information(self, "成功", "员工添加成功")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"添加员工失败: {str(e)}")
                
    def refresh_employee_list(self):
        try:
            employees = self.api_client.get_employees()
            self.employee_table.setRowCount(len(employees))
            for i, emp in enumerate(employees):
                # ID
                id_item = QTableWidgetItem(str(emp["id"]))
                id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                # 用户名
                username_item = QTableWidgetItem(emp["username"])
                username_item.setFlags(username_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                # 初始密码 (默认为123456)
                password_item = QTableWidgetItem("123456")
                password_item.setFlags(password_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                # 状态
                status_item = QTableWidgetItem("✓ 已启用" if emp["is_active"] else "✗ 已停用")
                status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if emp["is_active"]:
                    status_item.setForeground(Qt.GlobalColor.darkGreen)
                else:
                    status_item.setForeground(Qt.GlobalColor.red)
                
                self.employee_table.setItem(i, 0, id_item)
                self.employee_table.setItem(i, 1, username_item)
                self.employee_table.setItem(i, 2, password_item)
                self.employee_table.setItem(i, 3, status_item)
                
                # 操作按钮布局
                operation_widget = QWidget()
                operation_layout = QHBoxLayout(operation_widget)
                operation_layout.setContentsMargins(0, 0, 0, 0)
                
                # 启用/停用按钮
                toggle_button = QPushButton("停用" if emp["is_active"] else "启用")
                toggle_button.setStyleSheet(
                    "QPushButton { background-color: #ff4d4d; }" if emp["is_active"] 
                    else "QPushButton { background-color: #4CAF50; }"
                )
                toggle_button.clicked.connect(
                    lambda checked, eid=emp["id"], active=emp["is_active"]: 
                    self.toggle_employee_status(eid, not active)
                )
                
                # 删除按钮
                delete_button = QPushButton("删除")
                delete_button.setStyleSheet("QPushButton { background-color: #ff4d4d; }")
                delete_button.clicked.connect(lambda checked, eid=emp["id"]: self.delete_employee(eid))
                
                operation_layout.addWidget(toggle_button)
                operation_layout.addWidget(delete_button)
                self.employee_table.setCellWidget(i, 4, operation_widget)
                
            # 调整列宽
            self.employee_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            for i in [0, 2, 3, 4]:
                self.employee_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载员工列表失败: {str(e)}")
            
    def refresh_current_task(self):
        try:
            task = self.api_client.get_current_task()
            if task:
                self.current_task_label.setText(f"当前任务: {task['url']}")
            else:
                self.current_task_label.setText("当前无活动任务")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载当前任务失败: {str(e)}")
            
    def refresh_stats(self):
        try:
            date = self.date_picker.date().toPyDate()
            stats = self.api_client.get_daily_statistics(date)
            
            self.stats_table.setRowCount(len(stats))
            for i, stat in enumerate(stats):
                self.stats_table.setItem(i, 0, QTableWidgetItem(stat["username"]))
                self.stats_table.setItem(i, 1, QTableWidgetItem(str(stat["total_records"])))
                self.stats_table.setItem(i, 2, QTableWidgetItem(str(stat["success_count"])))
                self.stats_table.setItem(i, 3, QTableWidgetItem(str(stat["failure_count"])))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载统计数据失败: {str(e)}")
            
    def toggle_employee_status(self, employee_id: int, new_status: bool):
        try:
            self.api_client.update_employee_status(employee_id, new_status)
            self.refresh_employee_list()
            QMessageBox.information(self, "成功", "员工状态更新成功")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"更新员工状态失败: {str(e)}")
            
    def delete_employee(self, employee_id: int):
        reply = QMessageBox.question(
            self, 
            "确认删除", 
            "确定要删除该员工吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.api_client.delete_employee(employee_id)
                self.refresh_employee_list()
                QMessageBox.information(self, "成功", "员工删除成功")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除员工失败: {str(e)}")

    # 添加当前任务标签属性
    @property
    def current_task_label(self):
        # 任务信息现在显示在表格中，返回第一行的URL单元格
        if self.task_table.rowCount() > 0:
            for row in range(self.task_table.rowCount()):
                if self.task_table.item(row, 2) and self.task_table.item(row, 2).text() == "活动":
                    return self.task_table.item(row, 1)
        # 如果没有活动任务，返回空字符串
        return QTableWidgetItem("")
        
    def load_default_url(self):
        """加载默认URL"""
        try:
            import json
            from pathlib import Path
            
            config_path = Path('./data/config.json')
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    if 'default_url' in config:
                        self.url_input.setText(config['default_url'])
        except Exception as e:
            print(f"加载默认URL失败: {e}")
    
    def save_default_url(self, url):
        """保存默认URL"""
        try:
            import json
            from pathlib import Path
            
            config_path = Path('./data/config.json')
            config = {}
            
            # 如果配置文件存在，先读取现有配置
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
            
            # 更新默认URL
            config['default_url'] = url
            
            # 确保目录存在
            config_path.parent.mkdir(exist_ok=True)
            
            # 保存配置
            with open(config_path, 'w') as f:
                json.dump(config, f)
                
        except Exception as e:
            print(f"保存默认URL失败: {e}")

    def load_task_list(self):
        """加载任务列表"""
        try:
            tasks = self.api_client.get_all_tasks()
            
            # 清空表格
            self.task_table.setRowCount(0)
            
            if not tasks:
                return
                
            # 填充表格
            for row, task in enumerate(tasks):
                self.task_table.insertRow(row)
                
                # ID
                id_item = QTableWidgetItem(str(task.get("id", "")))
                id_item.setData(Qt.ItemDataRole.UserRole, task.get("id"))
                self.task_table.setItem(row, 0, id_item)
                
                # URL
                url_item = QTableWidgetItem(task.get("url", ""))
                self.task_table.setItem(row, 1, url_item)
                
                # 状态
                status_text = "活动" if task.get("is_active", False) else "非活动"
                status_item = QTableWidgetItem(status_text)
                if task.get("is_active", False):
                    status_item.setForeground(Qt.GlobalColor.green)
                self.task_table.setItem(row, 2, status_item)
                
                # 已烧录/限制
                max_cards = task.get("max_cards", 0)
                burned_cards = task.get("burned_cards", 0)
                
                if max_cards > 0:
                    quota_text = f"{burned_cards}/{max_cards}"
                    if burned_cards >= max_cards:
                        quota_item = QTableWidgetItem(quota_text + " (已用完)")
                        quota_item.setForeground(Qt.GlobalColor.red)
                    else:
                        quota_item = QTableWidgetItem(quota_text)
                else:
                    quota_item = QTableWidgetItem(f"{burned_cards} (无限制)")
                self.task_table.setItem(row, 3, quota_item)
                
                # 创建时间
                created_at = task.get("created_at", "")
                if created_at:
                    # 去除末尾的Z和毫秒
                    if "." in created_at:
                        created_at = created_at.split(".")[0]
                    if created_at.endswith("Z"):
                        created_at = created_at[:-1]
                    # 格式化时间
                    created_at = created_at.replace("T", " ")
                self.task_table.setItem(row, 4, QTableWidgetItem(created_at))
                
                # 创建操作按钮
                edit_btn = QPushButton("编辑")
                delete_btn = QPushButton("删除")
                # 使用create_action_buttons方法创建带有激活按钮的操作区
                actions_widget = self.create_action_buttons(edit_btn, delete_btn, task)
                self.task_table.setCellWidget(row, 5, actions_widget)
            
            # 调整列宽
            self.task_table.resizeColumnsToContents()
            self.task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            
        except Exception as e:
            print(f"加载任务列表失败: {e}")
            QMessageBox.warning(self, "错误", f"加载任务列表失败: {str(e)}")
            
    def edit_task(self, task_id):
        """编辑任务"""
        try:
            # 获取任务列表中的数据
            row = -1
            for r in range(self.task_table.rowCount()):
                item = self.task_table.item(r, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == task_id:
                    row = r
                    break
                    
            if row == -1:
                QMessageBox.warning(self, "错误", "找不到要编辑的任务")
                return
                
            # 获取当前任务数据
            url = self.task_table.item(row, 1).text()
            
            # 配额信息
            quota_text = self.task_table.item(row, 3).text()
            max_cards = 0
            if "无限制" not in quota_text and "/" in quota_text:
                max_cards = int(quota_text.split("/")[1].split(" ")[0])
            
            # 创建编辑对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("编辑任务")
            dialog.setMinimumWidth(400)
            
            dialog_layout = QVBoxLayout(dialog)
            
            # URL输入
            url_layout = QHBoxLayout()
            url_layout.addWidget(QLabel("烧录URL:"))
            url_edit = QLineEdit(url)
            url_layout.addWidget(url_edit)
            
            # 配额输入
            quota_layout = QHBoxLayout()
            quota_layout.addWidget(QLabel("卡片数量限制:"))
            quota_edit = QSpinBox()
            quota_edit.setRange(0, 9999)
            quota_edit.setValue(max_cards)
            quota_edit.setSpecialValueText("无限制")
            quota_layout.addWidget(quota_edit)
            
            # 按钮
            btn_layout = QHBoxLayout()
            save_btn = QPushButton("保存")
            cancel_btn = QPushButton("取消")
            btn_layout.addWidget(save_btn)
            btn_layout.addWidget(cancel_btn)
            
            dialog_layout.addLayout(url_layout)
            dialog_layout.addLayout(quota_layout)
            dialog_layout.addLayout(btn_layout)
            
            # 连接按钮事件
            save_btn.clicked.connect(dialog.accept)
            cancel_btn.clicked.connect(dialog.reject)
            
            # 显示对话框
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # 获取编辑后的数据
                new_url = url_edit.text().strip()
                new_max_cards = quota_edit.value()
                
                if not new_url:
                    QMessageBox.warning(self, "错误", "URL不能为空")
                    return
                    
                # 更新任务
                task_data = {
                    "url": new_url,
                    "max_cards": new_max_cards
                }
                
                result = self.api_client.update_task(task_id, task_data)
                if result:
                    QMessageBox.information(self, "成功", "任务更新成功")
                    self.load_task_list()
                    self.load_current_task()
                else:
                    QMessageBox.warning(self, "错误", "任务更新失败")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"编辑任务时发生异常: {str(e)}")
            
    def delete_task(self, task_id):
        """删除任务"""
        try:
            # 确认删除
            confirm = QMessageBox.question(
                self,
                "确认删除",
                "确定要删除这个任务吗？删除后无法恢复，并且相关的烧录记录也会被删除。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if confirm == QMessageBox.StandardButton.Yes:
                success = self.api_client.delete_task(task_id)
                if success:
                    QMessageBox.information(self, "成功", "任务已删除")
                    self.load_task_list()
                    self.load_current_task()
                else:
                    QMessageBox.warning(self, "错误", "删除任务失败")
                    
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除任务时发生异常: {str(e)}")

    def create_action_buttons(self, edit_btn, delete_btn, task):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # 获取任务ID
        task_id = task.get("id")
        
        # 添加编辑按钮
        edit_btn.clicked.connect(lambda checked=False, tid=task_id: self.edit_task(tid))
        layout.addWidget(edit_btn)
        
        # 添加删除按钮
        delete_btn.clicked.connect(lambda checked=False, tid=task_id: self.delete_task(tid))
        layout.addWidget(delete_btn)
        
        # 添加激活按钮，只有在任务非活动状态时显示
        if not task.get('is_active'):
            activate_btn = QPushButton("激活")
            activate_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
            activate_btn.clicked.connect(lambda checked=False, tid=task_id: self.activate_task(tid))
            layout.addWidget(activate_btn)
        
        return widget

    def activate_task(self, task_id):
        """激活指定ID的任务"""
        if not task_id:
            QMessageBox.warning(self, "错误", "无法获取任务ID")
            return
        
        try:
            # 调用API激活任务
            response = self.api_client.activate_task(task_id)
            
            if response:
                QMessageBox.information(self, "成功", f"任务已激活")
                # 刷新任务列表
                self.load_task_list()
            else:
                QMessageBox.warning(self, "错误", "激活任务失败")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"激活任务时发生错误: {str(e)}") 