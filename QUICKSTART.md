# 烧录工具启动指南

> 从零启动 / 调试 `nfctools` 客户端

---

## 一、环境准备

### 1.1 Python 版本

需要 **Python 3.10+**。检查：
```bash
python3 --version
```

### 1.2 安装依赖

```bash
cd /Users/zhou/Desktop/week/nfctools

# 推荐创建虚拟环境（避免污染系统 Python）
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**⚠️ macOS 注意**：`pyscard` 依赖 PC/SC 系统库：
```bash
# macOS 自带 PC/SC 框架，通常无需额外安装
# 如果 pip install pyscard 失败，试试：
brew install swig
pip install pyscard
```

**⚠️ Windows 注意**：需要先安装 ACR122U 读卡器驱动：
- https://www.acs.com.hk/en/driver/3/acr122u-usb-nfc-reader/

### 1.3 确认配置

检查 `config.json`：
```json
{
    "host": "https://nurafamily.com",
    "api_prefix": "/factory/legacy"
}
```

---

## 二、工厂账号准备

### 2.1 登录 Nurplay 管理后台创建工厂账号

1. 打开 `nurplay-admin` Web 后台
2. 进入 **工厂生态 → 工厂账号**
3. 新建账号，填写 `username` / `password` / `factory_id`
4. 保存，把账号密码发给工厂员工

### 2.2 创建一个测试用工单

1. 进入 **工厂生态 → NFC 工单管理**
2. 点击 **创建工单**
3. 填写：
   - **工单号**：`ORD-TEST-001`
   - **卡片类型**：选 `内容卡` / `录音卡` / `家庭卡` 任一
   - **SKU**：随便选一个
   - **工厂**：选你要测试的工厂
   - **数量**：10（测试少一点）
   - **内容卡** → 选一个内容组；**录音卡/家庭卡** → 直接填数量
4. 状态选 `pending`（等待生产）或 `producing`（进行中）
5. 保存

---

## 三、启动烧录工具

### 3.1 直接运行

```bash
cd /Users/zhou/Desktop/week/nfctools
source .venv/bin/activate    # 进入虚拟环境（如果用了）
python run.py
```

### 3.2 登录

1. 弹出登录窗口
2. 输入工厂账号密码（刚才在 Web 后台创建的）
3. 点**登录**

### 3.3 烧录流程

登录成功后进入主窗口，会自动：
1. 每 5 秒轮询 `GET /factory/legacy/burning/task/status/`
2. 显示当前工单的 URL / 剩余数量 / 已烧录数
3. 等待放卡

**没有 NFC 读卡器**时，主窗口会显示读卡器未连接。你依然可以验证：
- 登录是否成功
- 工单是否正确拉取
- 界面是否正常

**有 NFC 读卡器**时：
1. 把空白 NFC 卡放上去
2. 工具自动读取卡 UID → 生成随机 user_id → 写入 URL 到卡
3. 上报 `POST /factory/legacy/burning/sync`
4. 成功后工单的 `bound_count` +1

---

## 四、调试技巧

### 4.1 不带读卡器调试

如果你只想测试后端对接（没有读卡器），可以**改一下 NFC 逻辑模拟刷卡**：

```python
# 临时在 client/nfc_reader.py 里 mock
def read_nfc_id(self):
    import random
    return f"TEST{random.randint(10000000, 99999999):08X}"

def write_url_to_nfc(self, url):
    print(f"[MOCK] 模拟写入 URL: {url}")
    return True
```

### 4.2 看日志

工具里有 `print()` 日志，直接在终端看。关键日志：
- `获取任务失败: ...` — 网络或认证问题
- `创建记录失败: ...` — 上报接口问题
- `未授权创建记录，转为离线模式` — token 过期

### 4.3 直接用 curl 测试接口

```bash
# 1. 登录拿 token
curl -X POST https://nurafamily.com/factory/legacy/token \
  -d "username=YOUR_USERNAME" \
  -d "password=YOUR_PASSWORD"
# 响应：{"access_token":"xxx","token_type":"bearer","expires_in":604800}

# 2. 拉当前工单
curl https://nurafamily.com/factory/legacy/burning/task/status/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# 3. 模拟上报一条烧录记录
curl -X POST https://nurafamily.com/factory/legacy/burning/sync \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{"task_id": 1, "status": true, "user_id": "TESTUSER1234", "nfc_id": "04ABCDEF", "retry_count": 0}]'
```

### 4.4 清理离线数据

如果工具卡在"同步离线"状态：
```bash
rm ./data/offline_records.json
```

---

## 五、常见错误

| 现象 | 原因 | 解决 |
|------|------|------|
| 登录报 `连接服务器失败` | 网络 / 域名错 | 检查 `config.json` 的 host |
| 登录报 `账号或密码错误` | 账号未创建或禁用 | 去 Web 后台确认账号状态 |
| 登录成功但主界面"无任务" | 工单不属于该工厂或已 completed | 检查工单 `factory_id` 和 `status` |
| `pyscard` 安装失败 | 缺 swig / PCSC 库 | macOS: `brew install swig`; Linux: `apt install libpcsclite-dev` |
| 读卡器找不到 | 驱动问题 | Windows 装 ACR122U 驱动 |
| ImportError: No module named 'PyQt6' | 依赖未装 / 没激活虚拟环境 | `source .venv/bin/activate && pip install -r requirements.txt` |

---

## 六、打包发布

给工厂分发时打包成单 exe：

```bash
# Windows 下打包
pip install pyinstaller
python build_client.py
```

产物在 `dist/` 目录，工厂员工只需双击 exe + `config.json` 放同目录即可。

---

## 七、清单：验证完整流程

建议按这个顺序测一遍：

- [ ] 依赖装好，`python run.py` 能启动登录窗口
- [ ] 工厂账号能登录成功
- [ ] 登录成功跳到主窗口（不是 AdminWindow）
- [ ] 主窗口显示了当前工单的 URL 和数量
- [ ] 用 curl 模拟上报一条记录，数据库里 `nfc_tags` 多了一条记录
- [ ] 工单的 `bound_count` 自动 +1
- [ ] 烧录满额后工单自动 `completed`

---

## 八、项目文件导览

```
nfctools/
├── run.py                  ← 启动入口（这就是你要运行的文件）
├── config.json             ← 服务器地址配置
├── requirements.txt        ← Python 依赖
├── MIGRATION_TO_NURPLAY.md ← 迁移细节
├── QUICKSTART.md           ← 本文档
├── client/                 ← PyQt6 客户端源码
│   ├── app.py             ← 主应用入口
│   ├── login.py           ← 登录窗口
│   ├── main_window.py     ← 烧录主界面
│   ├── api_client.py      ← HTTP 客户端（已对接 Nurplay）
│   ├── nfc_reader.py      ← NFC 读写协议
│   └── config.py          ← 配置加载
├── data/                   ← 运行时数据（离线记录等，自动生成）
├── assets/                 ← 声音文件
├── config/                 ← 登录记住的用户名（自动生成）
│
├── backend/                ← ⚠️ 旧 FastAPI 后端，已废弃
├── nfc-backend-worker/     ← ⚠️ 旧 Workers 后端，已废弃
└── nfccloudflare/          ← ⚠️ 旧 KV 脚本，已废弃
```

---

## 需要我帮你执行启动吗？

告诉我：
- 你在 macOS / Windows / Linux？
- 有没有 NFC 读卡器插着？

我可以一步步帮你跑起来。
