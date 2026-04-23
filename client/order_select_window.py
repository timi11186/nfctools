"""工单选择页面：登录成功后显示，员工从列表里挑一个工单再进入烧录页面。"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QAbstractItemView,
    QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from .api_client import APIClient


class _OrderListFetcher(QThread):
    """后台拉取工单列表，避免阻塞 UI 线程（保证刷新动画能转起来）。"""
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, api_client):
        super().__init__()
        self.api_client = api_client

    def run(self):
        try:
            orders = self.api_client.list_available_orders()
            self.done.emit(orders or [])
        except Exception as e:
            self.failed.emit(str(e))


CARD_LABEL = {
    'content': '📀 内容卡',
    'recording': '🎙️ 录音卡',
    'family': '👨\u200d👩\u200d👧 家庭卡',
}


def _merge_summary(summary):
    """把 contents_summary 按 (card_type, group_id) 合并，避免每条都显示成 1/1。"""
    merged = {}
    order_keys = []
    for item in summary or []:
        ct = item.get('card_type', '?')
        gid = item.get('group_id') if ct == 'content' else None
        key = (ct, gid)
        if key not in merged:
            merged[key] = {'card_type': ct, 'group_id': gid, 'quantity': 0, 'burned': 0}
            order_keys.append(key)
        merged[key]['quantity'] += item.get('quantity', 0)
        merged[key]['burned'] += item.get('burned', 0)

    parts = []
    content_groups = sum(1 for k in merged if k[0] == 'content')
    for key in order_keys:
        e = merged[key]
        ct = e['card_type']
        label = CARD_LABEL.get(ct, ct)
        # 去图标只剩文字（给纯文本场景用）
        plain = label.split(' ', 1)[-1] if ' ' in label else label
        if ct == 'content' and e['group_id'] and content_groups > 1:
            plain += f"({e['group_id'][:6]})"
        parts.append(f"{plain} {e['burned']}/{e['quantity']}")
    return " | ".join(parts) if parts else "(无内容)"


class OrderSelectWindow(QWidget):
    # 选好一个工单后发出：order_id
    order_selected = pyqtSignal(int)

    def __init__(self, api_client: APIClient):
        super().__init__()
        self.api_client = api_client
        self.orders = []
        self._fetcher = None
        # 刷新动画用的小图标（旋转的省略号），文字是 "刷新中 ."/".."/"..."
        self._spinner_frames = ["刷新中 .  ", "刷新中 .. ", "刷新中 ..."]
        self._spinner_idx = 0
        from PyQt6.QtCore import QTimer
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(200)
        self._spinner_timer.timeout.connect(self._tick_spinner)
        self.init_ui()
        self.refresh_orders()

    def init_ui(self):
        self.setWindowTitle("NFC 烧录系统 - 选择工单")
        self.resize(720, 480)
        layout = QVBoxLayout(self)

        header = QLabel("请选择要烧录的工单")
        header.setStyleSheet("font-size: 16px; font-weight: bold; padding: 8px;")
        layout.addWidget(header)

        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #666; padding: 0 8px 4px 8px;")
        layout.addWidget(self.hint_label)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_orders)
        self.confirm_btn = QPushButton("开始烧录此工单")
        self.confirm_btn.setStyleSheet("font-weight: bold;")
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)

    def _tick_spinner(self):
        """驱动刷新按钮的加载动画。"""
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        self.refresh_btn.setText(self._spinner_frames[self._spinner_idx])

    def _set_refreshing(self, on: bool):
        if on:
            self.refresh_btn.setEnabled(False)
            self.confirm_btn.setEnabled(False)
            self._spinner_idx = 0
            self.refresh_btn.setText(self._spinner_frames[0])
            self._spinner_timer.start()
            # 覆盖提示告诉用户
            self.hint_label.setText("正在向服务器拉取最新工单列表...")
            # 让光标变成忙碌
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            self._spinner_timer.stop()
            self.refresh_btn.setText("刷新")
            self.refresh_btn.setEnabled(True)
            self.confirm_btn.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def refresh_orders(self):
        """异步刷新：启动后台线程抓列表，主线程播放动画。"""
        # 若上一次请求还没结束，避免重复触发
        if self._fetcher and self._fetcher.isRunning():
            return
        self._set_refreshing(True)
        self._fetcher = _OrderListFetcher(self.api_client)
        self._fetcher.done.connect(self._on_orders_loaded)
        self._fetcher.failed.connect(self._on_orders_failed)
        self._fetcher.start()

    def _on_orders_failed(self, err: str):
        self._set_refreshing(False)
        self.hint_label.setText(f"加载工单列表失败：{err}")
        self.list_widget.clear()

    def _on_orders_loaded(self, orders: list):
        self._set_refreshing(False)
        self.orders = orders
        self.list_widget.clear()

        if not self.orders:
            self.hint_label.setText("当前没有可烧录的工单。请联系管理员在后台创建工单。")
            return

        self.hint_label.setText(f"共 {len(self.orders)} 个工单（producing 优先显示，双击直接进入烧录）")

        for order in self.orders:
            oid = order.get('id')
            status = order.get('status')
            quantity = order.get('quantity', 0)
            bound = order.get('bound_count', 0)
            remaining = order.get('remaining', 0)
            next_ct = order.get('next_card_type', '?')
            next_label = CARD_LABEL.get(next_ct, next_ct)
            summary = _merge_summary(order.get('contents_summary') or [])

            title = (
                f"工单 #{oid}  [{status}]   "
                f"总量 {quantity}  已烧 {bound}  剩余 {remaining}\n"
                f"    配额分布: {summary}\n"
                f"    下一张: {next_label}"
            )
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, oid)
            if status == 'producing':
                item.setForeground(Qt.GlobalColor.darkGreen)
            if remaining <= 0:
                item.setForeground(Qt.GlobalColor.gray)
            self.list_widget.addItem(item)

        # 默认选中第一个
        self.list_widget.setCurrentRow(0)

    def _current_order_id(self):
        item = self.list_widget.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_double_click(self, _item):
        self._on_confirm()

    def _on_confirm(self):
        oid = self._current_order_id()
        if oid is None:
            QMessageBox.information(self, '提示', '请先选择一个工单。')
            return
        # 找到对应订单，判断是否已经烧完
        chosen = next((o for o in self.orders if o.get('id') == oid), None)
        if chosen and chosen.get('remaining', 0) <= 0:
            QMessageBox.warning(self, '工单已完成', f'工单 #{oid} 已烧录完成，无剩余配额。')
            return
        self.api_client.set_selected_order(oid)
        self.order_selected.emit(int(oid))
        self.close()
