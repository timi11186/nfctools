import sys
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from pathlib import Path
from .login import LoginWindow
from .main_window import MainWindow
from .api_client import APIClient
# 注意：admin_window 已随旧后端下线（功能迁移到 nurplay-admin Web 后台）
# 保留 import 以便本地开发需要时临时启用
try:
    from .admin_window import AdminWindow
except Exception:
    AdminWindow = None

class NFCBurningApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.api_client = APIClient()
        self.init_resources()
        
    def init_resources(self):
        # 确保资源目录存在
        assets_dir = Path("./assets")
        assets_dir.mkdir(exist_ok=True)
        
        # 检查声音文件是否存在，不存在则创建默认声音文件
        self.create_default_sounds(assets_dir)
        
    def create_default_sounds(self, assets_dir: Path):
        """创建默认的声音文件"""
        success_sound = assets_dir / "success.wav"
        fail_sound = assets_dir / "fail.wav"
        
        if not success_sound.exists():
            # 这里我们使用系统提示音，实际使用时可以替换为自定义声音文件
            import shutil
            try:
                # Windows系统提示音
                windows_sound = Path("C:/Windows/Media/chimes.wav")
                if windows_sound.exists():
                    shutil.copy(windows_sound, success_sound)
            except:
                print("无法创建成功提示音")
                
        if not fail_sound.exists():
            try:
                # Windows系统错误提示音
                windows_sound = Path("C:/Windows/Media/Windows Error.wav")
                if windows_sound.exists():
                    shutil.copy(windows_sound, fail_sound)
            except:
                print("无法创建失败提示音")
    
    def handle_login_success(self, token: str, user_type: str):
        """处理登录成功事件

        新后端（Nurplay）统一使用员工（factory_operator/factory_admin）流程，
        管理员相关功能（建工单/员工/统计）已迁移到 nurplay-admin Web 后台，
        客户端不再提供 AdminWindow。
        """
        self.api_client.set_auth(token, user_type)
        self.main_window = MainWindow(self.api_client)
        self.main_window.show()
    
    def run(self):
        """运行应用程序"""
        # 显示登录窗口
        self.login_window = LoginWindow()
        self.login_window.login_success.connect(self.handle_login_success)
        self.login_window.show()
        
        # 运行应用程序
        return self.app.exec()

def main():
    """程序入口点"""
    app = NFCBurningApp()
    sys.exit(app.run())

if __name__ == "__main__":
    main() 