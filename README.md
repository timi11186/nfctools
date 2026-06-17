# NFC 烧录工具（nfctools）

工厂产线用的 PyQt6 桌面工具：工厂员工用 ACR122U 读卡器给 NFC 卡写入跳转链接，并把卡登记到 **Nurplay 后端**。烧录成功后自动生成卡片二维码。

> ⚠️ **架构已变更（2026-04）**：本工具早期对接「本地 FastAPI 后端（itasbeeh.shop）」，现已**完全对接 Cloudflare 上的 Nurplay 后端**（`https://nurafamily.com`），走 `/factory/legacy/*` 兼容接口。
> 本仓库里的 `backend/`、`nfc-backend-worker/`、`nfccloudflare/` 都是**旧后端，已废弃**，不要再部署（见 `backend/DEPRECATED.md`）。工单管理 / 员工管理 / 统计已迁到 [`NurplayBackend`](../NurplayBackend) + 管理后台 [`nurplay-admin`](../nurplay-admin)。

---

## 当前架构

```
工厂员工
  │  插 ACR122U 读卡器
  ▼
PyQt6 客户端 (client/, 入口 run.py)
  │  HTTPS（config.json: host + api_prefix=/factory/legacy）
  ▼
Nurplay 后端 (Cloudflare Workers, https://nurafamily.com)
  /factory/legacy/* 兼容接口 → D1 数据库 + Workers KV(NFC_UIDS)
```

写卡时，工具会把卡的 UID + 工单内容登记到后端；后端把 NFC_UIDS 写进 Workers KV。NFC 卡被刷到时，CDN/Worker 先查 KV，有记录才跳转到真正地址（防野卡）。

---

## 快速开始

详细步骤见 **[QUICKSTART.md](QUICKSTART.md)**。最短路径：

```bash
cd /Users/zhou/Desktop/week/nfctools
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # PyQt6 / requests / pyscard / qrcode[pil]
python run.py                             # 启动登录窗口
```

> macOS 上 `pyscard` 依赖系统自带 PC/SC，一般无需额外装；失败时 `brew install swig` 再装。
> Windows 需先装 [ACR122U 驱动](https://www.acs.com.hk/en/driver/3/acr122u-usb-nfc-reader/)。

**配置** `config.json`（和 `run.py` / 打包后的 exe 同目录）：

```json
{
  "host": "https://nurafamily.com",
  "api_prefix": "/factory/legacy"
}
```

---

## 主流程

1. **登录** —— `LoginWindow`，账号密码走 `POST /factory/legacy/token` 拿 token（员工 / 管理员）。
2. **选工单** —— `OrderSelectWindow`，`GET /factory/legacy/burning/orders` 列可烧工单，选一个进入主窗口。
3. **烧录** —— `MainWindow`，刷卡 → 读 UID → 写入跳转链接 → `POST /factory/legacy/burning/sync` 登记到后端 → 工单 bound_count +1。
4. **二维码** —— 烧录成功自动生成 `qrcodes/{uid}.png`，窗口内可显示 / 另存 / 打印（`client/qr_export.py`）。
5. **卡片管理（烧错卡）** —— 主窗口「卡片管理」按钮，查询 / 取消 / 重烧某张卡。详见 **[CARD_MANAGEMENT.md](CARD_MANAGEMENT.md)**。

离线时（断网）烧录记录会本地缓存，联网后自动补传（`api_client._handle_offline_mode` / `sync_offline_records`）。

---

## 后端接口一览（均在 `https://nurafamily.com/factory/legacy`）

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/token` | 登录拿 token |
| `GET`  | `/burning/orders` | 列可烧工单 |
| `GET`  | `/burning/task/status/` | 查当前任务 / 工单状态 |
| `POST` | `/burning/sync` | 上报一条烧录记录（也用于离线批量补传）|
| `GET`  | `/nfc/{nfc_uid}` | 查询某张卡（类型 / 工单 / 激活态）|
| `DELETE` | `/nfc/{nfc_uid}` | 取消烧录（硬删记录，物理卡可重烧）|

> 这些 `/factory/legacy/*` 接口的后端实现在 `NurplayBackend/src/router/factory`（兼容层，对接旧客户端协议）。

---

## 硬件

- **读卡器**：ACR122U 或兼容的 USB NFC 读卡器
- **NFC 卡**：NTAG213 / FM08

---

## 打包分发（给工厂员工）

```bash
python build_client.py        # PyInstaller 打包，产物在 dist/
```

工厂员工拿到 `dist/` 里的 exe，**和 `config.json` 放同目录**双击即可，无需装 Python。

---

## 目录结构

```
nfctools/
├── run.py                  ← 启动入口
├── config.json             ← 服务器地址配置（host + api_prefix）
├── requirements.txt        ← Python 依赖
├── build_client.py         ← 打包脚本（→ dist/）
├── client/                 ← PyQt6 客户端（当前在用）
│   ├── app.py              ← 主程序 / 窗口流转
│   ├── login.py            ← 登录窗口
│   ├── order_select_window.py ← 选工单
│   ├── main_window.py      ← 烧录主窗口
│   ├── card_manager_window.py ← 卡片管理（查询/取消）
│   ├── api_client.py       ← 后端 API 封装（/factory/legacy/*）
│   ├── nfc_reader.py       ← ACR122U 读写
│   └── qr_export.py        ← 二维码生成/导出
├── qrcodes/                ← 烧录成功生成的二维码 PNG
├── assets/ · data/         ← 资源 / 本地缓存（离线补传等）
│
├── backend/                ← ⚠️ 旧 FastAPI 后端，已废弃（见 backend/DEPRECATED.md）
├── nfc-backend-worker/     ← ⚠️ 旧 Workers 后端，已废弃
└── nfccloudflare/          ← ⚠️ 旧 KV 脚本，已废弃
```

---

## 故障排查

| 现象 | 可能原因 / 处理 |
|---|---|
| 读卡器未检测到 | 装驱动（Windows）；确认 ACR122U 已连接；macOS 一般免驱 |
| 登录报「连接服务器失败」 | 网络 / 域名错 → 检查 `config.json` 的 `host` |
| 启动报缺 `pyscard` / PyQt6 | `pip install -r requirements.txt`（先进虚拟环境）|
| 烧录后没出二维码 | 看 `qrcodes/` 目录权限；检查烧录是否真正 sync 成功 |

---

## 相关文档

- **[QUICKSTART.md](QUICKSTART.md)** —— 从零启动 / 调试 / 打包 完整步骤
- **[CARD_MANAGEMENT.md](CARD_MANAGEMENT.md)** —— 卡片管理（烧错卡的查询 / 取消 / 重烧）
- **[MIGRATION_TO_NURPLAY.md](MIGRATION_TO_NURPLAY.md)** —— 从本地后端迁到 Nurplay 的历史记录
- **[backend/DEPRECATED.md](backend/DEPRECATED.md)** —— 旧后端为什么废弃、迁去了哪
