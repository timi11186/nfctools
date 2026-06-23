# 服务器配置模板：复制为 config.json（放项目根 / 可执行文件同级目录）后按需修改。
# 产线默认连生产；如需连测试后端，把 host 改成测试地址即可。
SERVER_CONFIG = {
    "host": "https://nurafamily.com",   # 后端地址（产线生产）
    "api_prefix": "/factory/legacy"      # 工厂兼容接口前缀
}

# 注：API URL 由 api_client._url（host + api_prefix + path）统一构造，无需 get_api_url。
