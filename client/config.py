import json
import os
from pathlib import Path

# 默认配置（产线工具默认连生产；开发/测试可在 config.json 覆盖 host）
DEFAULT_CONFIG = {
    'host': 'https://nurafamily.com',
    'api_prefix': '/factory/legacy',
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

# 注：API URL 由 api_client._url（host + api_prefix + path）统一构造。
# 旧的 get_api_url() 引用已废弃的 api_version（会 KeyError）、且无任何调用，已移除（BUG-022）。