"""
NFC 烧录工具 - API 客户端

已完全迁移到 Nurplay 后端（https://nurafamily.com）。
员工烧录功能通过 /factory/legacy/* 兼容接口访问。
管理员功能（建工单、建员工、看统计）已迁移到 nurplay-admin Web 后台，
客户端不再提供对应操作。
"""
import requests
from typing import Optional, List, Dict
from datetime import datetime
import json
from pathlib import Path
from . import config


class AdminFunctionDisabled(Exception):
    """管理员功能已迁移到 nurplay-admin Web 后台，客户端不再提供。"""
    pass


class APIClient:
    def __init__(self):
        self.token = None
        self.user_type = None
        # 员工在工单列表选定的工单 ID（None 表示未选，沿用后端默认策略）
        self.selected_order_id = None
        self.offline_data_path = Path('./data/offline_records.json')
        self.offline_data_path.parent.mkdir(exist_ok=True)

    # ---------- 基础 ----------

    @property
    def _host(self) -> str:
        return config.SERVER_CONFIG['host'].rstrip('/')

    @property
    def _api_prefix(self) -> str:
        # 兼容旧 config.json 没有 api_prefix 字段的情况
        return config.SERVER_CONFIG.get('api_prefix', '/factory/legacy')

    def _url(self, path: str) -> str:
        """构造 API URL：host + api_prefix + path"""
        return f"{self._host}{self._api_prefix}{path}"

    def set_auth(self, token: str, user_type: str):
        self.token = token
        self.user_type = user_type

    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.token}'
        } if self.token else {}

    # ---------- 离线记录 ----------

    def _handle_offline_mode(self, record: Dict):
        try:
            if self.offline_data_path.exists():
                with open(self.offline_data_path, 'r') as f:
                    offline_records = json.load(f)
            else:
                offline_records = []

            offline_records.append(record)

            with open(self.offline_data_path, 'w') as f:
                json.dump(offline_records, f)

            return True
        except Exception as e:
            print(f"保存离线数据失败: {e}")
            return False

    def sync_offline_records(self) -> bool:
        """
        同步离线队列。逐条检查后端 per-record 状态：
          - status=ok        → 删除该条
          - 永久错误         → 删除该条 + 写入 ./data/permanent_failures.json 留档报警
          - 临时错误 / 网络异常 → 保留在 offline 队列继续重试
        """
        if not self.offline_data_path.exists():
            return True

        try:
            with open(self.offline_data_path, 'r') as f:
                offline_records = json.load(f)

            if not offline_records:
                return True

            response = requests.post(
                self._url('/burning/sync'),
                headers=self._get_headers(),
                json=offline_records,
                timeout=15,
            )

            if response.status_code != 200:
                # 整体失败，整批保留下次重试
                return False

            try:
                results = response.json()
                if isinstance(results, dict):
                    results = results.get('results', [])
            except Exception:
                # 旧后端不返 JSON：按全成功处理（保留旧行为）
                self.offline_data_path.unlink()
                return True

            # 把响应按 nfc_id 索引一下，便于映射回原 record
            index = {}
            if isinstance(results, list):
                for r in results:
                    if isinstance(r, dict) and r.get('nfc_id'):
                        index[r.get('nfc_id')] = r

            remaining = []
            permanent_failures = []
            ok_count = 0
            for rec in offline_records:
                nfc_id = rec.get('nfc_id')
                resp = index.get(nfc_id)
                if not resp or resp.get('status') == 'ok':
                    ok_count += 1
                    continue
                err_msg = resp.get('msg') or resp.get('message') or '未知错误'
                if self._is_permanent_error(err_msg):
                    permanent_failures.append({**rec, 'reason': err_msg})
                    print(f"[sync_offline_records] 永久失败丢弃 nfc_id={nfc_id} msg={err_msg}")
                else:
                    remaining.append(rec)

            # 保留临时失败的继续等下次重试
            if remaining:
                with open(self.offline_data_path, 'w') as f:
                    json.dump(remaining, f)
            else:
                self.offline_data_path.unlink()

            # 永久失败留档供运维查看
            if permanent_failures:
                try:
                    perm_path = self.offline_data_path.parent / 'permanent_failures.json'
                    existing = []
                    if perm_path.exists():
                        with open(perm_path, 'r') as f:
                            existing = json.load(f)
                    existing.extend(permanent_failures)
                    with open(perm_path, 'w') as f:
                        json.dump(existing, f)
                except Exception as e:
                    print(f"保存永久失败记录出错: {e}")

            print(f"[sync_offline_records] ok={ok_count} retry={len(remaining)} dropped={len(permanent_failures)}")
            return len(remaining) == 0

        except Exception as e:
            print(f"同步离线数据失败: {e}")
            return False

    # ---------- 员工操作（已对接 /factory/legacy/*） ----------

    def get_current_task(self):
        """获取当前活动的烧录任务（兼容旧代码，内部调用 task/status）"""
        status = self.get_task_status()
        if not status or not status.get('has_task'):
            return None
        # 映射为旧格式，避免 UI 层改动
        return {
            'id': status.get('id'),
            'url': status.get('url'),
            'is_active': status.get('is_active', True),
            'max_cards': status.get('max_cards', 0),
            'burned_cards': status.get('burned_cards', 0),
        }

    def _cache_current_task(self, task_data: Dict) -> None:
        try:
            task_cache_path = Path('./data/current_task.json')
            task_cache_path.parent.mkdir(exist_ok=True)
            with open(task_cache_path, 'w') as f:
                json.dump(task_data, f)
        except Exception as e:
            print(f"缓存任务失败: {str(e)}")

    def _load_cached_task(self) -> Optional[Dict]:
        try:
            task_cache_path = Path('./data/current_task.json')
            if task_cache_path.exists():
                with open(task_cache_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载缓存任务失败: {str(e)}")
        return None

    def list_available_orders(self) -> List[Dict]:
        """列出本工厂所有 producing/pending 工单，供员工选择。"""
        try:
            response = requests.get(
                self._url('/burning/orders'),
                headers=self._get_headers(),
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('orders', []) if data.get('success') else []
            elif response.status_code == 401:
                print("未授权：请重新登录")
            return []
        except Exception as e:
            print(f"获取工单列表失败: {e}")
            return []

    def set_selected_order(self, order_id: Optional[int]):
        """设置当前员工选中的工单 ID。"""
        self.selected_order_id = int(order_id) if order_id is not None else None

    def get_task_status(self) -> Optional[Dict]:
        """获取任务状态和卡片限制信息"""
        try:
            params = {}
            if self.selected_order_id:
                params['order_id'] = self.selected_order_id
            response = requests.get(
                self._url('/burning/task/status/'),
                headers=self._get_headers(),
                params=params or None,
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                print("未授权：请重新登录")
            return None
        except Exception as e:
            print(f"获取任务状态失败: {e}")
            return None

    # 后端拒绝消息里命中以下关键词视为"永久错误" —— 即便重试也不可能成功
    # （工单已 completed / 配额满 / 员工没分配到这个工单 / 工单不存在）
    # 这种情况下离线重试只会让脏数据越积越多，应直接告警让用户处理（重置工单 / 报废卡）。
    _PERMANENT_ERROR_KEYWORDS = (
        'quota exhausted',
        'order not found',
        'not assigned',
        'completed',
        'cancelled',
    )

    @classmethod
    def _is_permanent_error(cls, msg: str) -> bool:
        if not msg:
            return False
        low = msg.lower()
        return any(k in low for k in cls._PERMANENT_ERROR_KEYWORDS)

    def create_burning_record(self, record_data: dict) -> Dict:
        """
        上报单条烧录记录。

        返回 dict（过去返回 bool —— 当时只看 HTTP 200 就当成功，导致后端
        per-record 'status:error' 被忽略；现在改成统一返回带详细信息的字典）：
          {'ok': True}                                        ✅ 后端确认入库
          {'ok': False, 'error': msg, 'permanent': bool,
           'queued_offline': bool, 'queued_for_retry': bool}  ❌ 失败/拒收

        约定：
          - 非永久错误（网络异常、HTTP 非 200/401、500 等）→ 进 offline 队列下次重试
          - 永久错误（quota / order completed / not assigned）→ 不进 offline，
            UI 应弹明显警告：物理卡已写但 DB 没记录，要么重置工单要么报废这张卡
        """
        try:
            response = requests.post(
                self._url('/burning/sync'),
                headers=self._get_headers(),
                json=[record_data],  # 服务端接受数组
                timeout=15,
            )
        except Exception as e:
            msg = f"网络异常：{e}"
            print(f"创建记录异常: {e}")
            queued = self._handle_offline_mode(record_data)
            return {'ok': False, 'error': msg, 'permanent': False,
                    'queued_offline': queued, 'queued_for_retry': True}

        if response.status_code == 401:
            print("未授权创建记录，转为离线模式")
            queued = self._handle_offline_mode(record_data)
            return {'ok': False, 'error': '未授权（请重新登录）', 'permanent': False,
                    'queued_offline': queued, 'queued_for_retry': True}

        if response.status_code != 200:
            print(f"创建记录失败: {response.status_code} {response.text}")
            queued = self._handle_offline_mode(record_data)
            return {'ok': False, 'error': f"HTTP {response.status_code}",
                    'permanent': False,
                    'queued_offline': queued, 'queued_for_retry': True}

        # 200 OK —— 还要看 per-record 的 status，关键 bug 修复点
        try:
            results = response.json()
            if isinstance(results, dict):
                # 兼容 {results: [...]}
                results = results.get('results', [])
        except Exception:
            # 旧后端可能不返 JSON 数组，回退保留原行为
            return {'ok': True}

        if not isinstance(results, list) or len(results) == 0:
            return {'ok': True}

        # 我们一次只发一条，所以只看第一个结果
        rec = results[0] if isinstance(results[0], dict) else {}
        rec_status = rec.get('status')

        if rec_status == 'ok':
            return {'ok': True}

        # status='error' 或其他非 ok 状态
        err_msg = rec.get('msg') or rec.get('message') or '后端拒收'
        permanent = self._is_permanent_error(err_msg)
        queued = False if permanent else self._handle_offline_mode(record_data)
        print(f"[create_burning_record] 后端拒收 (permanent={permanent}): {err_msg}")
        return {'ok': False, 'error': err_msg, 'permanent': permanent,
                'queued_offline': queued, 'queued_for_retry': not permanent}

    # ---------- 卡片管理（查询 / 取消烧录 / 重烧） ----------

    def query_nfc_card(self, nfc_uid: str) -> Optional[Dict]:
        """
        查询某张 NFC 卡的当前状态。
        返回:
          {
            "found": True/False,
            "nfc_uid": "...",
            "type": "content" | "recording" | "family",
            "group_id": "..." | None,
            "status": "active" | "disabled" | "blacklisted",
            "create_time": "ISO...",
            "activated_time": "ISO..." | None,
            "can_cancel": True
          }
        未找到时 found=False。
        """
        try:
            response = requests.get(
                self._url(f'/nfc/{nfc_uid.strip()}'),
                headers=self._get_headers(),
                timeout=10,
            )
            if response.status_code == 200:
                payload = response.json()
                if payload.get('success'):
                    return payload.get('data') or {}
                return {'found': False, 'error': payload.get('message')}
            elif response.status_code == 401:
                return {'found': False, 'error': '未授权，请重新登录'}
            else:
                return {'found': False, 'error': f'HTTP {response.status_code}: {response.text[:200]}'}
        except Exception as e:
            return {'found': False, 'error': f'网络错误: {e}'}

    def cancel_nfc_card(self, nfc_uid: str, order_id: Optional[int] = None) -> Dict:
        """
        取消某张 NFC 卡的烧录（硬删除后端记录 + 递减工单 bound_count）。
        物理卡未来可以重新烧录（走正常流程写入新记录）。

        参数:
          nfc_uid: 必填
          order_id: 可选，明确对应工单 ID；不传则由后端回退到当前 producing 工单

        返回:
          {
            "success": True,
            "nfc_uid": "...",
            "deleted": True,
            "decremented_order_id": 123 | None
          }
        """
        body = {}
        if order_id is not None:
            body['order_id'] = int(order_id)

        try:
            response = requests.delete(
                self._url(f'/nfc/{nfc_uid.strip()}'),
                headers={**self._get_headers(), 'Content-Type': 'application/json'},
                json=body if body else None,
                timeout=10,
            )
            data = None
            try:
                data = response.json()
            except Exception:
                pass

            if response.status_code == 200 and data and data.get('success'):
                return {'success': True, **(data.get('data') or {})}
            elif response.status_code == 404:
                return {'success': False, 'error': (data or {}).get('message', '卡片不存在')}
            elif response.status_code == 403:
                return {'success': False, 'error': (data or {}).get('message', '无权限')}
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}: {response.text[:200]}'}
        except Exception as e:
            return {'success': False, 'error': f'网络错误: {e}'}

    # ---------- 管理员功能（已下线，迁移到 Web 后台） ----------

    _ADMIN_DISABLED_MSG = (
        "该管理员功能已迁移到 Nurplay 管理后台 (nurplay-admin)。\n"
        "请联系管理员通过 Web 管理后台创建/管理 NFC 生产工单和工厂账号。"
    )

    def create_employee(self, data: dict) -> dict:
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def get_employees(self) -> List[dict]:
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def update_employee_status(self, employee_id: int, is_active: bool) -> dict:
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def delete_employee(self, employee_id: int) -> dict:
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def get_daily_statistics(self, date) -> List[dict]:
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def create_task(self, task_data):
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def set_burning_task(self, task_data):
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def get_all_tasks(self):
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def update_task(self, task_id, task_data):
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def delete_task(self, task_id):
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)

    def activate_task(self, task_id):
        raise AdminFunctionDisabled(self._ADMIN_DISABLED_MSG)
