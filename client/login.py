from PyQt6.QtWidgets import (QWidget, QLabel, QLineEdit, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QCheckBox, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
import requests
import json
from pathlib import Path
from . import config

class LoginWindow(QWidget):
    # 登录成功信号
    login_success = pyqtSignal(str, str)  # token, user_type
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_saved_username()
        
    def init_ui(self):
        self.setWindowTitle('NFC烧录系统 - 登录')
        self.setFixedSize(300, 200)
        
        # 创建布局
        layout = QVBoxLayout()
        
        # 用户名输入
        username_layout = QHBoxLayout()
        username_label = QLabel('用户名:')
        self.username_input = QLineEdit()
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        
        # 密码输入
        password_layout = QHBoxLayout()
        password_label = QLabel('密码:')
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        
        # 记住账号密码选项
        self.remember_checkbox = QCheckBox('记住账号密码')
        
        # 登录按钮
        self.login_button = QPushButton('登录')
        self.login_button.clicked.connect(self.handle_login)
        
        # 添加所有控件到主布局
        layout.addLayout(username_layout)
        layout.addLayout(password_layout)
        layout.addWidget(self.remember_checkbox)
        layout.addWidget(self.login_button)
        
        # 设置布局
        self.setLayout(layout)
        
    def load_saved_username(self):
        try:
            config_path = Path('./config/login.json')
            if config_path.exists():
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    # 兼容旧字段名 remember_username
                    if data.get('remember_credentials') or data.get('remember_username'):
                        self.username_input.setText(data.get('username', ''))
                        self.password_input.setText(data.get('password', ''))
                        self.remember_checkbox.setChecked(True)
        except Exception as e:
            print(f"加载保存的账号失败: {e}")

    def save_username(self):
        try:
            config_path = Path('./config/login.json')
            config_path.parent.mkdir(exist_ok=True)

            remember = self.remember_checkbox.isChecked()
            data = {
                'remember_credentials': remember,
                'username': self.username_input.text() if remember else '',
                'password': self.password_input.text() if remember else '',
            }

            with open(config_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"保存账号失败: {e}")
            
    def handle_login(self):
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, '错误', '请输入用户名和密码')
            return

        # 对接 Nurplay 后端的 legacy 兼容接口：
        # POST {host}/factory/legacy/token
        # Form-encoded: username, password
        # 响应: { access_token, token_type, expires_in }
        host = config.SERVER_CONFIG['host'].rstrip('/')
        api_prefix = config.SERVER_CONFIG.get('api_prefix', '/factory/legacy')

        try:
            response = requests.post(
                f"{host}{api_prefix}/token",
                data={
                    'username': username,
                    'password': password
                },
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                self.save_username()

                # 新后端的工厂账号统一走员工流程（admin 功能已迁移到 Web 后台）
                # 保留 user_type 字段避免上层兼容问题
                user_type = 'employee'

                token = data.get('access_token') or data.get('token')
                if not token:
                    QMessageBox.warning(self, '错误', f'登录响应缺少 token: {data}')
                    return

                self.login_success.emit(token, user_type)
                self.close()
            elif response.status_code in (400, 401):
                try:
                    msg = response.json().get('message') or response.json().get('detail') or '用户名或密码错误'
                except Exception:
                    msg = '用户名或密码错误'
                QMessageBox.warning(self, '错误', msg)
            else:
                QMessageBox.warning(self, '错误', f'登录失败: HTTP {response.status_code}\n{response.text[:200]}')

        except requests.RequestException as e:
            QMessageBox.critical(self, '错误', f'连接服务器失败: {e}')
