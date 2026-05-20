"""工单选择页面：登录成功后显示，员工从列表里挑一个工单再进入烧录页面。"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QAbstractItemView,
    QApplication, QFrame, QGroupBox, QFormLayout, QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from .api_client import APIClient
from .qr_export import render_card_qr, qr_available

try:
    import smartcard.System
    from smartcard.Exceptions import NoCardException, CardConnectionException
    HAS_SMARTCARD = True
except ImportError:
    HAS_SMARTCARD = False


CARD_TYPE_LABEL_FULL = {
    'content': '📀 内容卡',
    'recording': '🎙️ 录音卡',
    'family': '👨‍👩‍👧 家庭卡',
}

STATUS_LABEL = {
    'active': '✅ active',
    'disabled': '⛔ disabled',
    'blacklisted': '🚫 blacklisted',
}


def _read_hardware_uid() -> str | None:
    """直接通过 smartcard APDU 读一次卡片硬件 UID（不依赖 NFCReader 烧录线程）。

    与 card_manager_window._read_hardware_uid 同款实现，方便复用。
    返回大写 hex 字符串，未读到 / 出错返 None。
    """
    if not HAS_SMARTCARD:
        return None
    try:
        readers = smartcard.System.readers()
        if not readers:
            return None
        connection = readers[0].createConnection()
        connection.connect()
        # APDU: GET UID  FF CA 00 00 00
        response, sw1, _sw2 = connection.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
        try:
            connection.disconnect()
        except Exception:
            pass
        if sw1 == 0x90:
            return ''.join(f'{b:02X}' for b in response)
        return None
    except (NoCardException, CardConnectionException):
        return None
    except Exception as e:
        print(f"[OrderSelect] 读卡异常: {e}")
        return None


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


ROLE_LABEL = {
    'mama': '妈妈',
    'papa': '爸爸',
    'child': '孩子',
}


def _merge_summary(summary):
    """把 contents_summary 按 (card_type, group_id, preset_role) 合并，避免每条都显示成 1/1。
    v9.5：家庭卡按 preset_role 分桶，让"100 张爸爸 + 100 张妈妈"分两段显示。"""
    merged = {}
    order_keys = []
    for item in summary or []:
        ct = item.get('card_type', '?')
        gid = item.get('group_id') if ct == 'content' else None
        role = item.get('preset_role') if ct == 'family' else None
        key = (ct, gid, role)
        if key not in merged:
            merged[key] = {'card_type': ct, 'group_id': gid, 'preset_role': role, 'quantity': 0, 'burned': 0}
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
        if ct == 'family' and e['preset_role']:
            plain += f"·{ROLE_LABEL.get(e['preset_role'], e['preset_role'])}"
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
        self._current_qr_pixmap = None   # 当前卡二维码（全分辨率，内存，不落盘）
        self._current_qr_uid = None
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
        # 卡片检测区加了二维码后内容变高，窗口相应加高
        self.resize(720, 720)
        self.setMinimumSize(620, 640)
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

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #ddd; margin: 8px 0;")
        layout.addWidget(sep)

        # 卡片检测区
        check_box = QGroupBox("🔍 卡片检测（核对手上的卡是否真的是后端记录的那一张）")
        check_box.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 14px; }")
        check_layout = QVBoxLayout(check_box)

        check_btn_row = QHBoxLayout()
        self.check_card_btn = QPushButton("📡 检测卡片")
        self.check_card_btn.setStyleSheet("padding: 6px 18px;")
        self.check_card_btn.clicked.connect(self._on_check_card)
        check_btn_row.addWidget(self.check_card_btn)
        check_btn_row.addStretch()
        check_layout.addLayout(check_btn_row)

        self.check_result_label = QLabel("把卡放到读卡器上，点上面「检测卡片」按钮。")
        self.check_result_label.setStyleSheet(
            "color: #555; padding: 6px; background: #f8f8f8; border-radius: 4px;"
        )
        self.check_result_label.setWordWrap(True)
        self.check_result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        check_layout.addWidget(self.check_result_label)

        # 认领二维码：检测到卡片后显示，可另存 / 打印
        qr_row = QHBoxLayout()
        self.qr_label = QLabel("检测到卡片后显示二维码")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setMinimumSize(170, 170)
        self.qr_label.setStyleSheet("color: #999; background: #f8f8f8; border-radius: 4px;")
        qr_row.addWidget(self.qr_label)

        qr_btn_col = QVBoxLayout()
        self.btn_qr_save = QPushButton("另存为图片…")
        self.btn_qr_save.clicked.connect(self.handle_qr_save)
        self.btn_qr_save.setEnabled(False)
        self.btn_qr_print = QPushButton("打印二维码")
        self.btn_qr_print.clicked.connect(self.handle_qr_print)
        self.btn_qr_print.setEnabled(False)
        qr_btn_col.addWidget(self.btn_qr_save)
        qr_btn_col.addWidget(self.btn_qr_print)
        qr_btn_col.addStretch()
        qr_row.addLayout(qr_btn_col)
        check_layout.addLayout(qr_row)

        if not HAS_SMARTCARD:
            self.check_card_btn.setEnabled(False)
            self.check_result_label.setText("⚠️ 未安装 smartcard 库，本机无法检测卡片。")

        layout.addWidget(check_box)

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

    # ---------- 卡片检测 ----------

    def _on_check_card(self):
        """读硬件 UID + 调后端 query_nfc_card，把后端记录的卡片信息显示给员工核对。

        典型用途：员工手上的卡跟"系统认为他要烧的那张"对不对得上——
        刷一下，看 UID + type + status + group_id 是不是预期的。
        """
        if not HAS_SMARTCARD:
            QMessageBox.warning(self, '无读卡器', '本机未安装 smartcard 库，无法检测。')
            return

        # 每次检测先清掉上一次的二维码，成功路径再重新显示
        self._clear_qr()

        # 1. 读硬件 UID
        try:
            if not smartcard.System.readers():
                self.check_result_label.setText("⚠️ 未检测到读卡器，请检查 USB 连接。")
                return
        except Exception as e:
            self.check_result_label.setText(f"⚠️ 读卡器异常：{e}")
            return

        self.check_card_btn.setEnabled(False)
        self.check_card_btn.setText("📡 读卡中...")
        QApplication.processEvents()

        try:
            uid = _read_hardware_uid()
            if not uid:
                self.check_result_label.setText("⚠️ 没读到卡。请把卡稳定放在读卡器上再点一次。")
                return

            # 2. 后端查询
            try:
                info = self.api_client.query_nfc_card(uid)
            except Exception as e:
                self.check_result_label.setText(
                    f"📛 UID = {uid}\n查询后端失败：{e}"
                )
                return

            # 3. 渲染结果
            if not info or not info.get('found'):
                self.check_result_label.setText(
                    f"📛 UID = {uid}\n后端无此卡记录（这张卡还没烧过 / 工厂没烧成功 / 已被删）。"
                )
                return

            ct = info.get('type') or '?'
            ct_label = CARD_TYPE_LABEL_FULL.get(ct, ct)
            status = info.get('status') or '?'
            status_label = STATUS_LABEL.get(status, status)
            group_id = info.get('group_id')
            preset_role = info.get('preset_role')
            create_time = info.get('create_time') or ''
            activated = info.get('activated_time') or '尚未激活'

            lines = [
                f"📇 UID:        {uid}",
                f"📂 卡片类型:    {ct_label}",
                f"💡 状态:        {status_label}",
            ]
            if ct == 'content':
                lines.append(f"🎵 内容组:      {group_id or '(未绑定)'}")
            elif ct == 'family':
                # v9.5：家庭卡显示预设角色
                if preset_role:
                    lines.append(f"👪 预设角色:    {ROLE_LABEL.get(preset_role, preset_role)} ({preset_role})")
                else:
                    lines.append(f"👪 预设角色:    未预设（App 端扫到时让用户选）")
            lines.append(f"🏭 烧录时间:    {create_time}")
            lines.append(f"⚡ 首次激活:    {activated}")

            # 跟当前选中的工单做"是否匹配"提示（仅 content 卡有 group_id 比较意义）
            cur_oid = self._current_order_id()
            chosen = next((o for o in self.orders if o.get('id') == cur_oid), None)
            if chosen and ct == 'content' and group_id:
                # 看选中的工单 contents_summary 里有没有这个 group_id
                summary = chosen.get('contents_summary') or []
                expected_groups = {
                    s.get('group_id') for s in summary
                    if s.get('card_type') == 'content' and s.get('group_id')
                }
                if expected_groups and group_id in expected_groups:
                    lines.append(f"\n✅ 该卡匹配当前选中工单 #{cur_oid}")
                elif expected_groups:
                    lines.append(
                        f"\n⚠️ 该卡的 group_id 不在工单 #{cur_oid} 的配额里："
                        f"工单要求 {sorted(expected_groups)[:3]}..."
                    )

            self.check_result_label.setText("\n".join(lines))
            self._show_qr(uid)
        finally:
            self.check_card_btn.setEnabled(True)
            self.check_card_btn.setText("📡 检测卡片")

    # ---------- 认领二维码 ----------

    def _show_qr(self, uid: str):
        """生成并显示该卡的认领二维码（内存渲染，不落盘）。"""
        if not uid:
            self._clear_qr()
            return
        if not qr_available():
            self._current_qr_pixmap = None
            self._current_qr_uid = None
            self.btn_qr_save.setEnabled(False)
            self.btn_qr_print.setEnabled(False)
            self.qr_label.clear()
            self.qr_label.setText("未安装 qrcode 依赖")
            return
        data = render_card_qr(uid)
        if data:
            pix = QPixmap()
            if pix.loadFromData(data, 'PNG') and not pix.isNull():
                self._current_qr_pixmap = pix
                self._current_qr_uid = uid
                self.qr_label.setText("")
                self.qr_label.setPixmap(pix.scaled(
                    160, 160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                self.btn_qr_save.setEnabled(True)
                self.btn_qr_print.setEnabled(True)
                return
        self._current_qr_pixmap = None
        self._current_qr_uid = None
        self.btn_qr_save.setEnabled(False)
        self.btn_qr_print.setEnabled(False)
        self.qr_label.clear()
        self.qr_label.setText("二维码生成失败")

    def _clear_qr(self):
        self._current_qr_pixmap = None
        self._current_qr_uid = None
        self.qr_label.clear()
        self.qr_label.setText("检测到卡片后显示二维码")
        self.qr_label.setStyleSheet("color: #999; background: #f8f8f8; border-radius: 4px;")
        self.btn_qr_save.setEnabled(False)
        self.btn_qr_print.setEnabled(False)

    def handle_qr_save(self):
        """把当前二维码另存到用户选定位置（此处才真正写文件）。"""
        if not self._current_qr_pixmap or self._current_qr_pixmap.isNull():
            QMessageBox.warning(self, '无二维码', '请先检测一张卡片。')
            return
        default_name = f'{self._current_qr_uid or "qr"}.png'
        target, _ = QFileDialog.getSaveFileName(
            self, '保存二维码', default_name, 'PNG 图片 (*.png)',
        )
        if not target:
            return
        if self._current_qr_pixmap.save(target, 'PNG'):
            QMessageBox.information(self, '已保存', f'二维码已保存到：\n{target}')
        else:
            QMessageBox.critical(self, '保存失败', '无法写入该位置，请换个目录。')

    def handle_qr_print(self):
        """打印当前二维码。"""
        if not self._current_qr_pixmap or self._current_qr_pixmap.isNull():
            QMessageBox.warning(self, '无二维码', '请先检测一张卡片。')
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return
        try:
            painter = QPainter(printer)
            page = printer.pageRect(QPrinter.Unit.DevicePixel)
            scaled = self._current_qr_pixmap.scaled(
                int(page.width()), int(page.height()),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = int((page.width() - scaled.width()) / 2)
            y = int((page.height() - scaled.height()) / 2)
            painter.drawPixmap(x, y, scaled)
            painter.end()
        except Exception as e:
            QMessageBox.critical(self, '打印失败', str(e))
