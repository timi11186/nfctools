# NFC 烧录工具 → Nurplay 后端迁移文档

> 日期：2026-04-16
> 目标：将 `nfctools` PyQt6 客户端从旧版 `itasbeeh.shop` 后端完全迁移到 Nurplay 统一后端 `https://nurafamily.com`。

---

## 一、改动概览

### 1.1 保留的功能

- ✅ **员工烧录界面**（`MainWindow`）— 完整保留，通过兼容接口对接新后端
- ✅ **NFC 硬件协议**（`nfc_reader.py`）— 不动（NTAG213 / FM08 读写逻辑与后端无关）
- ✅ **离线模式** — 离线记录仍存 `./data/offline_records.json`，联网后批量 sync
- ✅ **声音提示、重试逻辑、UI 布局** — 不变

### 1.2 下线的功能

- ❌ **管理员界面（AdminWindow）** — 所有管理员功能（创建工单/员工/看统计）迁移到 **Nurplay 管理后台 Web**：
  - 网址：`https://nurplay-admin.pages.dev` 或本地 `http://localhost:3001`
  - 入口：工单管理、工厂账号管理、NFC 标签查询等
- ❌ **旧版 FastAPI 后端** (`backend/`) — 不再部署和维护，源码保留备查
- ❌ **独立的 NFC Workers 后端** (`nfc-backend-worker/`) — 已合并入主后端

---

## 二、端点映射

| 旧端点（itasbeeh.shop） | 新端点（nurafamily.com） | 备注 |
|----|----|----|
| `POST /token` (form) | `POST /factory/legacy/token` (form) | 完全兼容，返回 `access_token` 格式一致 |
| `GET /burning/task/status/` | `GET /factory/legacy/burning/task/status/` | 响应字段完全兼容 |
| `POST /burning/sync` | `POST /factory/legacy/burning/sync` | 请求体格式完全兼容 |
| `POST /admin/employees/` | ❌ 已下线 | 改用 Web 后台 |
| `POST /admin/tasks/` | ❌ 已下线 | 改用 Web 后台 |
| `GET /admin/statistics/daily` | ❌ 已下线 | 改用 Web 后台 |
| 其他 admin 端点 | ❌ 已下线 | 调用会抛 `AdminFunctionDisabled` |

---

## 三、配置变更

### `config.json`

```diff
  {
-     "host": "https://itasbeeh.shop"
+     "host": "https://nurafamily.com",
+     "api_prefix": "/factory/legacy"
  }
```

`api_prefix` 是新增字段，所有 API 路径会自动拼接这个前缀。默认 `/factory/legacy`。

---

## 四、代码改动详情

### 4.1 `client/api_client.py`

- 所有员工端点走 `self._url(path)`，自动加 `/factory/legacy` 前缀
- 登录方法不再存在（LoginWindow 自己发登录请求）
- `get_current_task()` 改为内部转调 `get_task_status()`，返回旧格式便于上层兼容
- Admin 相关方法全部改为抛 `AdminFunctionDisabled` 异常

### 4.2 `client/login.py`

- 登录请求路径：`{host}/token` → `{host}/factory/legacy/token`
- 响应格式不变：`{ access_token, token_type, expires_in }`
- 用户类型统一按 `employee` 处理（不再区分 admin）
- 增加了超时设置和错误消息解析

### 4.3 `client/app.py`

- 登录成功后不再判断 admin/employee，一律进入 `MainWindow`
- `AdminWindow` 改为可选 import（保留源码但默认不启用）

### 4.4 保留的文件

- `client/admin_window.py`, `admin_login.py`, `admin_registration.py` — 保留源码，不再挂载
- `backend/`, `nfc-backend-worker/`, `nfccloudflare/` — 各目录加了 `DEPRECATED.md`

---

## 五、部署步骤

### 5.1 本地开发测试

```bash
cd /Users/zhou/Desktop/week/nfctools
python run.py
```

1. 登录窗口输入 Nurplay 工厂账号（由 Nurplay 管理员在 Web 后台创建）
2. 成功后进入烧录界面
3. 自动轮询 `GET /factory/legacy/burning/task/status/` 显示当前工单
4. 刷卡烧录后上报 `POST /factory/legacy/burning/sync`

### 5.2 打包 Windows 可执行

```bash
python build_client.py
```

产物在 `dist/` 目录，客户端会读取当前目录下的 `config.json`。

### 5.3 分发给工厂

**工厂需要做的事**：
1. 更新 `config.json` 为新地址
2. 使用 Nurplay 管理员发的新工厂账号登录
3. 旧账号密码作废

**后端需要做的事**：
1. Nurplay 管理员在 Web 后台创建工厂工单（指定 `card_type`）
2. 为每个工厂员工创建工厂账号（`role: factory_operator`）
3. 把工单分配给对应工厂

---

## 六、Admin 功能迁移指引

旧客户端的管理员做的事，现在在 Nurplay Web 后台完成：

| 旧操作 | 新位置 |
|-----|-----|
| 创建员工 | `nurplay-admin` → 工厂生态 → 工厂账号 |
| 创建工单 | `nurplay-admin` → 工厂生态 → NFC 工单管理 → 创建 |
| 激活/修改工单 | 工单管理页面 |
| 查看日统计 | 工单详情 → 统计 |
| Cloudflare KV 配置 | 已无需（后端已内置 UID 跳转逻辑） |

---

## 七、回滚方案

如果新后端出问题，回滚步骤：

1. 恢复 `config.json`：
   ```json
   {"host": "https://itasbeeh.shop"}
   ```
2. 重启 `backend/main.py`（FastAPI 服务）
3. 客户端重新打包分发

**但这是应急方案**，长期维护请使用 Nurplay 后端。

---

## 八、兼容性测试清单

- [ ] 工厂账号能正常登录
- [ ] 能拉到进行中的 NFC 工单
- [ ] 显示剩余数量（`max_cards - burned_cards`）
- [ ] 成功刷卡上报后 `bound_count` 递增
- [ ] 失败刷卡上报后 `failed_count` 递增
- [ ] 离线模式：断网烧录 → 联网后自动 sync
- [ ] 超出 quota 后工单自动 `completed`
- [ ] 不同 `card_type` 的工单（content / recording / family）都能正确烧录

---

## 九、联系信息

- 后端代码库：`/Users/zhou/Desktop/week/NurplayBackend`
- 管理后台代码库：`/Users/zhou/Desktop/week/nurplay-admin`
- 烧录工具代码库：`/Users/zhou/Desktop/week/nfctools`（本目录）
