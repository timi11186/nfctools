import json
import os
from pathlib import Path

# 默认配置
DEFAULT_CONFIG = {
    'host': 'http://localhost:8000'
}

# 配置文件路径
CONFIG_FILE = Path("./config.json")
if not os.path.exists("./config.json"):
    # 如果是打包后的可执行文件，配置文件会在可执行文件目录
    exe_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent
    CONFIG_FILE = exe_dir / "config.json"

# 尝试加载配置文件
SERVER_CONFIG = DEFAULT_CONFIG.copy()
try:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            file_config = json.load(f)
            SERVER_CONFIG.update(file_config)
    else:
        # 创建默认配置文件
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
except Exception as e:
    print(f"加载配置文件失败: {e}, 使用默认配置")

# 保存配置
def save_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False

def get_api_url(endpoint: str) -> str:
    """获取完整的API URL"""
    return f"{SERVER_CONFIG['host']}/api/{SERVER_CONFIG['api_version']}/{endpoint}" 