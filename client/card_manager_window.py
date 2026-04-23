"""
NFC 卡片管理窗口

功能：
  1. 查询某张 NFC 卡在后端的状态（类型/所属工单/是否可取消）
  2. 取消烧录（硬删除后端记录，物理卡可重新烧录）
  3. 重烧流程（取消 → 引导回主窗口重新刷卡）

触发方式：
  - 通过扫 NFC 读卡器自动填入 UID（需放卡到读卡器）
  - 或手工输入 UID

使用场景：
  - 员工烧错卡（写进了错误的工单）
  - 卡片检测出现问题，需要清空记录后重烧
  - 查询某张卡目前的状态
"""
from PyQt6.QtWidgets import (
    QDialog, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QMessageBox, QTextEdit,
)
from PyQt6.QtCore import Qt, QTimer

try:
    import smartcard.System
    from smartcard.Exceptions import NoCardException, CardConnectionException
    HAS_SMARTCARD = True
except ImportError:
    HAS_SMARTCARD = False


CARD_TYPE_LABEL = {
    'content': '内容卡',
    'recording': '录音卡',
    'family': '家庭卡',
}

STATUS_LABEL = {
    'active': '激活',
    'disabled': '禁用',
    'blacklisted': '黑名单',
}


class CardManagerWindow(QDialog):
    def __init__(self, api_client, current_order_id=None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.current_order_id = current_order_id
        self._current_card_data = None
        self._init_ui()
        self._start_auto_scan()

    def _init_ui(self):
        self.setWindowTitle('NFC 卡片管理')
        self.setMinimumSize(520, 500)

        layout = QVBoxLayout(self)

        # —— 顶部说明 ——
        hint = QLabel(
            '在此查询/取消某张已烧录的 NFC 卡。\n'
            '• 自动读卡：把卡放到读卡器上，工具会自动识别\n'
            '• 手动输入：直接输入 UID 或逻辑 UID（写在卡上的 user_id）\n'
            '• 取消后该卡可重新烧录（物理卡不作废）'
        )
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #666; padding: 8px; background: #f5f5f5; border-radius: 4px;')
        layout.addWidget(hint)

        # —— UID 输入区 ——
        uid_box = QGroupBox('目标 NFC 卡')
        uid_layout = QHBoxLayout(uid_box)
        self.uid_input = QLineEdit()
        self.uid_input.setPlaceholderText('UID 或 user_id（按回车查询）')
        self.uid_input.returnPressed.connect(self.handle_query)
        uid_layout.addWidget(self.uid_input)

        self.btn_query = QPushButton('查询')
        self.btn_query.clicked.connect(self.handle_query)
        uid_layout.addWidget(self.btn_query)

        self.btn_read_nfc = QPushButton('读卡')
        self.btn_read_nfc.clicked.connect(self.handle_read_nfc)
        self.btn_read_nfc.setToolTip('点击此按钮读取当前放在读卡器上的卡')
        uid_layout.addWidget(self.btn_read_nfc)

        layout.addWidget(uid_box)

        # —— 查询结果 ——
        info_box = QGroupBox('卡片信息')
        info_layout = QFormLayout(info_box)
        self.lbl_found = QLabel('-')
        self.lbl_uid = QLabel('-')
        self.lbl_logic_uid = QLabel('-')
        self.lbl_type = QLabel('-')
        self.lbl_group = QLabel('-')
        self.lbl_status = QLabel('-')
        self.lbl_created = QLabel('-')
        self.lbl_activated = QLabel('-')

        for lbl in [self.lbl_found, self.lbl_uid, self.lbl_logic_uid, self.lbl_type,
                    self.lbl_group, self.lbl_status, self.lbl_created, self.lbl_activated]:
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        info_layout.addRow('状态：', self.lbl_found)
        info_layout.addRow('NFC UID：', self.lbl_uid)
        info_layout.addRow('Logic UID：', self.lbl_logic_uid)
        info_layout.addRow('卡片类型：', self.lbl_type)
        info_layout.addRow('内容组：', self.lbl_group)
        info_layout.addRow('卡片状态：', self.lbl_status)
        info_layout.addRow('创建时间：', self.lbl_created)
        info_layout.addRow('首次使用：', self.lbl_activated)
        layout.addWidget(info_box)

        # —— 操作按钮 ——
        action_layout = QHBoxLayout()

        self.btn_cancel = QPushButton('取消烧录（删除记录）')
        self.btn_cancel.setStyleSheet(
            'QPushButton { background: #d9534f; color: white; padding: 8px; font-weight: bold; }'
            'QPushButton:disabled { background: #ccc; }'
        )
        self.btn_cancel.clicked.connect(self.handle_cancel)
        self.btn_cancel.setEnabled(False)
        action_layout.addWidget(self.btn_cancel)

        self.btn_close = QPushButton('关闭')
        self.btn_close.clicked.connect(self.close)
        action_layout.addWidget(self.btn_close)
        layout.addLayout(action_layout)

        # —— 日志区 ——
        log_box = QGroupBox('操作日志')
        log_layout = QVBoxLayout(log_box)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_box)

    # ---------- 直接读卡（不依赖 NFCReader 烧录线程） ----------

    def _read_hardware_uid(self) -> str | None:
        """直接通过 smartcard 库读一次卡片硬件 UID，不创建线程。"""
        if not HAS_SMARTCARD:
            return None
        try:
            readers = smartcard.System.readers()
            if not readers:
                return None
            connection = readers[0].createConnection()
            connection.connect()
            # APDU: GET UID
            response, sw1, sw2 = connection.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
            try:
                connection.disconnect()
            except Exception:
                pass
            if sw1 == 0x90:
                return ''.join(f'{b:02X}' for b in response)
            return None
        except NoCardException:
            return None
        except CardConnectionException:
            return None
        except Exception as e:
            print(f"[CardManager] 读卡异常: {e}")
            return None

    def _start_auto_scan(self):
        """短轮询：如果用户把卡放上去且输入框为空，自动填入 UID"""
        if not HAS_SMARTCARD:
            self._log('⚠️ 未找到 smartcard 库，仅支持手动输入 UID')
            return
        # 先探测一下读卡器
        try:
            if not smartcard.System.readers():
                self._log('⚠️ 未检测到读卡器，仅支持手动输入 UID')
                return
        except Exception as e:
            self._log(f'⚠️ 读卡器检测失败: {e}')
            return

        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self._poll_reader)
        self.scan_timer.start(1500)

    def _poll_reader(self):
        """后台轻量轮询：输入框为空时自动读卡"""
        if self.uid_input.text().strip():
            return
        nfc_id = self._read_hardware_uid()
        if nfc_id:
            self.uid_input.setText(nfc_id)
            self._log(f'✓ 自动读取到硬件 UID: {nfc_id}')
            self.handle_query()

    # ---------- 核心操作 ----------

    def handle_read_nfc(self):
        if not HAS_SMARTCARD:
            QMessageBox.warning(self, '无读卡器', '未安装 smartcard 库，请使用手动输入。')
            return
        try:
            if not smartcard.System.readers():
                QMessageBox.warning(self, '无读卡器', '未检测到 NFC 读卡器。')
                return
        except Exception as e:
            QMessageBox.critical(self, '读卡器错误', str(e))
            return

        nfc_id = self._read_hardware_uid()
        if nfc_id:
            self.uid_input.setText(nfc_id)
            self._log(f'✓ 读取 UID: {nfc_id}')
            self.handle_query()
        else:
            QMessageBox.warning(self, '未读到卡', '请把卡放到读卡器上再点「读卡」。')

    def handle_query(self):
        uid = self.uid_input.text().strip()
        if not uid:
            QMessageBox.warning(self, '缺少 UID', '请输入或读取 UID')
            return

        self._log(f'→ 查询 UID={uid}')
        data = self.api_client.query_nfc_card(uid)

        if not data:
            self._log('✗ 查询失败（空响应）')
            self._clear_info()
            return

        if 'error' in data:
            self._log(f'✗ 查询失败: {data["error"]}')
            self._clear_info()
            QMessageBox.warning(self, '查询失败', data['error'])
            return

        if not data.get('found'):
            self._log(f'ℹ UID 未在后端注册（这张卡尚未被烧录）')
            self.lbl_found.setText('✗ 未找到（未烧录或已取消）')
            self.lbl_found.setStyleSheet('color: #999;')
            self.lbl_uid.setText(uid)
            self.lbl_logic_uid.setText('-')
            self.lbl_type.setText('-')
            self.lbl_group.setText('-')
            self.lbl_status.setText('-')
            self.lbl_created.setText('-')
            self.lbl_activated.setText('-')
            self.btn_cancel.setEnabled(False)
            self._current_card_data = None
            return

        # 找到了，显示信息
        self._current_card_data = data
        self.lbl_found.setText('✓ 已找到')
        self.lbl_found.setStyleSheet('color: #28a745; font-weight: bold;')
        self.lbl_uid.setText(data.get('nfc_uid', '-'))
        self.lbl_logic_uid.setText(data.get('logic_uid') or '-')
        card_type = data.get('type', '-')
        self.lbl_type.setText(f"{CARD_TYPE_LABEL.get(card_type, card_type)} ({card_type})")
        self.lbl_group.setText(data.get('group_id') or '（无）')
        status = data.get('status', '-')
        self.lbl_status.setText(f"{STATUS_LABEL.get(status, status)} ({status})")
        self.lbl_created.setText(data.get('create_time') or '-')
        self.lbl_activated.setText(data.get('activated_time') or '（从未使用）')

        can_cancel = data.get('can_cancel', False)
        self.btn_cancel.setEnabled(bool(can_cancel))
        self._log(f'✓ 查询成功: type={card_type}, status={status}')

    def handle_cancel(self):
        if not self._current_card_data:
            return

        uid = self._current_card_data.get('nfc_uid')
        card_type = self._current_card_data.get('type')
        ret = QMessageBox.question(
            self, '确认取消烧录',
            f'确定要取消这张卡的烧录记录吗？\n\n'
            f'UID: {uid}\n'
            f'类型: {CARD_TYPE_LABEL.get(card_type, card_type)}\n\n'
            f'⚠️ 这是硬删除操作：\n'
            f'• 后端记录将被删除\n'
            f'• 对应工单的已烧录数量 -1\n'
            f'• 物理卡不受影响，可重新烧录',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self._log(f'→ 取消烧录 UID={uid}，order_id={self.current_order_id}')

        result = self.api_client.cancel_nfc_card(uid, order_id=self.current_order_id)
        if result.get('success'):
            self._log(f'✓ 取消成功，已回滚工单 #{result.get("decremented_order_id")} 的计数')
            QMessageBox.information(
                self, '取消成功',
                f'UID {uid} 的烧录记录已删除。\n\n'
                f'这张物理卡现在可以重新放到读卡器上烧录。'
            )
            self.handle_query()  # 刷新显示
        else:
            err = result.get('error', '未知错误')
            self._log(f'✗ 取消失败: {err}')
            QMessageBox.critical(self, '取消失败', err)

    # ---------- 辅助 ----------

    def _clear_info(self):
        self.lbl_found.setText('-')
        self.lbl_found.setStyleSheet('')
        self.lbl_uid.setText('-')
        self.lbl_logic_uid.setText('-')
        self.lbl_type.setText('-')
        self.lbl_group.setText('-')
        self.lbl_status.setText('-')
        self.lbl_created.setText('-')
        self.lbl_activated.setText('-')
        self.btn_cancel.setEnabled(False)
        self._current_card_data = None

    def _log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime('%H:%M:%S')
        self.log_text.append(f'[{ts}] {msg}')

    def closeEvent(self, event):
        if getattr(self, 'scan_timer', None):
            self.scan_timer.stop()
        super().closeEvent(event)
