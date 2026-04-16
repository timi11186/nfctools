# 烧录工具 - 卡片管理功能

> 用于处理"烧错卡"等异常场景。员工可在工具内直接查询/取消/重烧某张 NFC 卡。

---

## 功能清单

| 功能 | 入口 | 说明 |
|------|-----|------|
| 查询卡片状态 | 主窗口「卡片管理」按钮 | 显示卡的类型、所属工单、激活状态等 |
| 取消烧录 | 卡片管理窗口 → 红色按钮 | 硬删除后端记录，物理卡可重新烧录 |
| 重烧 | 取消后关闭窗口 → 正常刷卡 | 不需要单独的重烧接口，走常规烧录流程 |

---

## 使用流程

### 场景 A：员工发现刚才烧错了一张

```
1. 在主窗口点击「卡片管理」
2. 把那张烧错的 NFC 卡放到读卡器上
3. 工具自动读取 UID 并查询后端
4. 显示卡片信息（类型、工单、UID）
5. 点「取消烧录（删除记录）」 → 确认
6. 后端删除记录 + 工单 bound_count -1
7. 关闭管理窗口
8. 再次刷同一张卡 → 正常烧录到当前工单
```

### 场景 B：员工把内容卡烧成了录音卡（错工单）

```
1. 发现问题，点击「卡片管理」
2. 读卡查询，确认类型是 recording（错的）
3. 取消 → 后端删除记录
4. 关闭管理窗口
5. 先让管理员调整工单：把当前工单改成 producing 的"内容卡"工单
   （或切换到已是 producing 状态的内容卡工单）
6. 再刷同一张卡 → 现在会被写入内容卡
```

### 场景 C：手动查询某个 UID

```
1. 点击「卡片管理」
2. 直接在输入框输入 UID（或 user_id），按回车
3. 查看状态，决定是否取消
```

---

## 后端接口（工厂侧）

### 查询卡片

```
GET /factory/legacy/nfc/{nfc_uid}
Authorization: Bearer {factory_token}
```

**响应**：
```json
{
  "success": true,
  "data": {
    "found": true,
    "nfc_uid": "A1B2C3D4E5F6G7H8",
    "logic_uid": "A1B2C3D4E5F6G7H8",
    "type": "recording",
    "group_id": null,
    "status": "active",
    "create_time": "2026-04-16T10:00:00.000Z",
    "activated_time": null,
    "can_cancel": true
  }
}
```

未找到时：
```json
{
  "success": true,
  "data": { "found": false, "nfc_uid": "..." }
}
```

### 取消烧录

```
DELETE /factory/legacy/nfc/{nfc_uid}
Authorization: Bearer {factory_token}
Content-Type: application/json

{ "order_id": 9 }    ← 可选，传了更精确；不传则回退到当前 producing 工单
```

**响应**：
```json
{
  "success": true,
  "data": {
    "nfc_uid": "A1B2C3D4E5F6G7H8",
    "deleted": true,
    "decremented_order_id": 9
  }
}
```

**后端行为**：
1. 记录一条日志到 `nfc_production_logs`（error_code=`CANCELLED`）
2. 硬删除 `nfc_tags` 记录（级联删除 `nfc_recordings` / `family_conversations`）
3. 工单 `bound_count - 1`
4. 如果工单之前因满额变成 `completed`，回退到 `producing` 状态

---

## 权限说明

- 工厂员工只要登录成功就能查询/取消**任意 UID**
- 取消操作会记录到工单日志，可追溯
- 建议未来增加「只能取消本工厂工单关联的卡」限制（当前为简化实现未做）

---

## 常见问题

| 问题 | 原因 | 解决 |
|-----|------|------|
| 查询返回「未找到」 | UID 尚未烧录 / 已被取消 | 正常现象 |
| 取消按钮灰掉 | `can_cancel: false` 或 UID 未找到 | 先查询确认状态 |
| 取消后 bound_count 没减 | 取消时没有匹配到对应工单 | 手动传 `order_id` 或检查工厂绑定 |
| 烧录中点不开管理窗口 | 读卡器冲突 | 先点「停止烧录」 |

---

## 代码文件

| 文件 | 作用 |
|------|------|
| `client/card_manager_window.py` | 管理窗口 UI + 逻辑 |
| `client/main_window.py` | 主窗口「卡片管理」按钮 + 打开逻辑 |
| `client/api_client.py` | `query_nfc_card()` / `cancel_nfc_card()` |
| （后端）`src/router/factory/legacy.ts` | 新增 `GET/DELETE /nfc/:uid` |

---

## 后续可能的增强

- [ ] 批量查询/取消多张卡（导入 UID 列表）
- [ ] 查询历史（本次会话已取消的卡列表）
- [ ] 限制只能取消本工厂的卡
- [ ] 增加 Undo（24h 内可恢复）
