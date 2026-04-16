# 服务器配置
SERVER_CONFIG = {
    "host": "http://your_server_ip:8000",  # 替换为实际的服务器地址
    "api_version": "v1"
}

def get_api_url(endpoint: str) -> str:
    """获取完整的API URL"""
    return f"{SERVER_CONFIG['host']}/api/{SERVER_CONFIG['api_version']}/{endpoint}" 