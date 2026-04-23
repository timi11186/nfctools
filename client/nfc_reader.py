from PyQt6.QtCore import QThread, pyqtSignal
import smartcard.System
from smartcard.Exceptions import NoCardException, CardConnectionException
import time
from typing import Optional, Tuple
import requests
import uuid
import string
import random
import hashlib

class NFCReader(QThread):
    status_changed = pyqtSignal(str)
    burning_complete = pyqtSignal(bool, str, str)  # 成功状态, 用户ID, NFC卡ID
    device_connected = pyqtSignal(bool)
    
    # NFC指令常量
    SELECT_NDEF = [0x00, 0xA4, 0x04, 0x00, 0x07, 0xD2, 0x76, 0x00, 0x00, 0x85, 0x01, 0x01]
    NTAG_GET_VERSION = [0xFF, 0x00, 0x00, 0x00, 0x02, 0x60, 0x00]
    NTAG_READ = [0xFF, 0xB0, 0x00]
    NTAG_WRITE = [0xFF, 0xD6, 0x00]
    FM08_READ = [0xFF, 0xB0, 0x00]
    FM08_WRITE = [0xFF, 0xD6, 0x00]
    
    NTAG_COMMANDS = {
        'GET_VERSION': [0x60, 0x00],
        'READ': [0x30],
        'WRITE': [0xA2],
        'PWD_AUTH': [0x1B],
        'READ_CNT': [0x39]
    }
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.current_url = None
        self.retry_count = 0
        self.max_retries = 3
        self.check_device()
        
    def check_device(self):
        try:
            readers = smartcard.System.readers()
            if readers:
                self.device_connected.emit(True)
                self.status_changed.emit("读卡器已连接")
                return True
            else:
                self.device_connected.emit(False)
                self.status_changed.emit("未检测到读卡器")
                return False
        except Exception as e:
            self.device_connected.emit(False)
            self.status_changed.emit(f"读卡器检测错误: {str(e)}")
            return False
        
    def set_url(self, url: str):
        self.current_url = url
        
    def start(self):
        self.running = True
        super().start()
        
    def stop(self):
        print("[NFC_READER] 收到 stop() 调用")
        self.running = False
        # 不阻塞 UI，线程会在 0.1-0.5 秒内自己退出
        # 只有卡片未移开时可能延迟几秒，调用方（open_card_manager）会再 wait 一次
        
    def run(self):
        print("[NFC_READER] 线程启动，进入主循环")
        self.running = True
        loop_count = 0
        while self.running:
            loop_count += 1
            try:
                readers = smartcard.System.readers()
                if not readers:
                    self.device_connected.emit(False)
                    self.status_changed.emit("未检测到读卡器")
                    # 快速检测 stop 信号，避免阻塞
                    for _ in range(10):
                        if not self.running:
                            print("[NFC_READER] 停止信号收到（无读卡器循环）")
                            return
                        time.sleep(0.1)
                    continue

                reader = readers[0]
                self.device_connected.emit(True)

                try:
                    connection = reader.createConnection()
                    connection.connect()  # 没有卡时抛 NoCardException
                    print(f"[NFC_READER] #{loop_count} 成功连接到卡 ATR={connection.getATR()}")

                    self.status_changed.emit("检测到NFC卡片，准备写入...")
                    time.sleep(0.2)

                    success = self.write_url_to_card(connection)
                    print(f"[NFC_READER] #{loop_count} write_url_to_card returned {success}")

                    if not success:
                        self.retry_count += 1
                        if self.retry_count >= self.max_retries:
                            self.retry_count = 0
                            time.sleep(1)
                        else:
                            self.status_changed.emit(f"烧录失败，正在重试({self.retry_count}/{self.max_retries})")
                            time.sleep(0.5)
                            continue
                    else:
                        self.retry_count = 0
                        time.sleep(0.5)

                    # 等用户拿走卡（connection 失效即退出）
                    wait_count = 0
                    while self.running:
                        wait_count += 1
                        if wait_count % 50 == 0:
                            print(f"[NFC_READER] 等待卡片移开... ({wait_count*0.1:.0f}s)")
                        try:
                            connection.getATR()
                            time.sleep(0.1)
                        except:
                            print("[NFC_READER] 卡片已移开")
                            break
                    if not self.running:
                        print("[NFC_READER] 等卡移开循环中收到停止信号")
                        return

                except NoCardException:
                    # 没卡时是常态，不打 print 避免刷屏，但通过 status_changed 告诉 UI
                    self.status_changed.emit("等待放置 NFC 卡片...")
                    # 快速轮询 + 对 stop 信号响应
                    for _ in range(5):
                        if not self.running:
                            print("[NFC_READER] 停止信号收到（等卡循环）")
                            return
                        time.sleep(0.1)
                except CardConnectionException as e:
                    print(f"[NFC_READER] CardConnectionException: {e}")
                    self.status_changed.emit("请重新放置卡片并保持稳定")
                    time.sleep(0.3)

            except Exception as e:
                import traceback
                print(f"[NFC_READER] 外层异常: {e}\n{traceback.format_exc()}")
                self.status_changed.emit(f"设备错误: {str(e)}")
                time.sleep(1)
        print("[NFC_READER] 主循环退出")

    def detect_card_type(self, connection) -> str:
        try:
            # 1. 先尝试 NTAG213 特有的命令
            self.status_changed.emit("正在检测NTAG213...")
            try:
                # 尝试读取第4页
                read_cmd = [0xFF, 0xB0, 0x00, 0x04, 0x04]
                response, sw1, sw2 = connection.transmit(read_cmd)
                if sw1 == 0x90:
                    # 再尝试写入一个测试页（比如第4页）
                    test_write = [0xFF, 0xD6, 0x00, 0x04, 0x04, 0x00, 0x00, 0x00, 0x00]
                    response, sw1, sw2 = connection.transmit(test_write)
                    if sw1 == 0x90:
                        self.status_changed.emit("确认为NTAG213卡片")
                        return "NTAG213"
            except:
                pass

            # 2. 尝试 FM08 特有的认证方式
            self.status_changed.emit("正在检测FM08...")
            try:
                # 加载默认密钥
                load_key_cmd = [0xFF, 0x82, 0x00, 0x00, 0x06] + [0xFF] * 6
                response, sw1, sw2 = connection.transmit(load_key_cmd)
                if sw1 == 0x90:
                    # 尝试认证块1
                    auth_cmd = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, 1, 0x60, 0x00]
                    response, sw1, sw2 = connection.transmit(auth_cmd)
                    if sw1 == 0x90:
                        self.status_changed.emit("确认为FM08卡片")
                        return "FM08"
            except:
                pass

            self.status_changed.emit("未能识别卡片类型")
            return ""

        except Exception as e:
            self.status_changed.emit(f"卡片检测异常: {str(e)}")
            return ""

    def generate_user_id(self, length=16):
        """生成随机用户ID，结合时间戳确保唯一性"""
        # 当前时间戳
        timestamp = str(int(time.time()))
        
        # 随机字符串
        random_str = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length-4))
        
        # 结合时间戳和随机字符创建种子
        seed = timestamp + random_str
        
        # 使用MD5创建哈希值
        hash_obj = hashlib.md5(seed.encode())
        hash_digest = hash_obj.hexdigest()
        
        # 取哈希值的前4位与随机字符组合
        unique_id = random_str + hash_digest[:4]
        
        # 确保长度符合要求
        if len(unique_id) > length:
            unique_id = unique_id[:length]
            
        return unique_id.upper()
        
    def get_nfc_id(self, connection) -> Optional[str]:
        """尝试获取NFC卡的唯一ID"""
        try:
            # 尝试读取卡片UID (卡片类型不同，指令可能不同)
            uid_cmd = [0xFF, 0xCA, 0x00, 0x00, 0x00]
            response, sw1, sw2 = connection.transmit(uid_cmd)
            
            if sw1 == 0x90:
                # 将UID转换为十六进制字符串
                uid = ''.join(f'{x:02X}' for x in response)
                return uid
            
            return None
        except Exception as e:
            self.status_changed.emit(f"读取NFC ID异常: {str(e)}")
            return None

    def write_url_to_card(self, connection) -> bool:
        try:
            # 先检测卡片类型
            card_type = self.detect_card_type(connection)
            if not card_type:
                self.status_changed.emit("无法识别的卡片类型")
                self.burning_complete.emit(False, "", "")
                return False

            # 读取NFC卡ID
            nfc_id = self.get_nfc_id(connection)
            if not nfc_id:
                self.status_changed.emit("无法读取NFC卡ID")
                # 继续执行，不强制要求NFC ID

            # 生成随机用户ID
            user_id = self.generate_user_id()
            self.status_changed.emit(f"生成用户ID: {user_id}")
            
            # 构建完整URL
            complete_url = self.current_url
            if "?" in complete_url:
                complete_url += f"&uid={user_id}"
            else:
                complete_url += f"?uid={user_id}"
                
            # 暂存原始URL
            original_url = self.current_url
            # 设置完整URL进行写入
            self.current_url = complete_url

            result = False
            if card_type == "NTAG213":
                self.status_changed.emit("开始写入NTAG213卡片...")
                result = self.write_ntag_213(connection)
            elif card_type == "FM08":
                self.status_changed.emit("开始写入FM08卡片...")
                result = self.write_fm08(connection)
            else:
                self.status_changed.emit("不支持的卡片类型")
                # 恢复原始URL
                self.current_url = original_url
                self.burning_complete.emit(False, "", "")
                return False

            # 恢复原始URL
            self.current_url = original_url
            
            # 打印调试信息
            print(f"烧录结果: {result}, 用户ID: {user_id}, NFC ID: {nfc_id if nfc_id else 'None'}")
                
            # 如果成功，发送用户ID和NFC ID
            if result:
                self.burning_complete.emit(True, user_id, nfc_id if nfc_id else "")
            else:
                self.burning_complete.emit(False, "", "")
                
            return result

        except Exception as e:
            self.status_changed.emit(f"写入异常: {str(e)}")
            self.burning_complete.emit(False, "", "")
            return False

    def write_ntag_213(self, connection) -> bool:
        try:
            # 检查是否有URL
            if not self.current_url:
                self.status_changed.emit("没有设置URL")
                return False
                
            # 准备NDEF数据
            url = self.current_url
            self.status_changed.emit(f"准备写入URL: {url}")
            
            if url.startswith("https://"):
                url = url[8:]  # 移除 https://
            url_bytes = list(url.encode('utf-8'))
            
            ndef_data = [
                0x03,  # NDEF Message Start
                len(url_bytes) + 5,  # Length
                0xD1,  # NDEF Record Header
                0x01,  # Type Length
                len(url_bytes) + 1,  # Payload Length
                0x55,  # Type: 'U'
                0x04,  # URL Prefix: "https://"
            ] + url_bytes + [0xFE]  # 添加结束标记

            # 先清空卡片
            self.status_changed.emit("正在清空卡片...")
            empty_page = [0x00] * 4
            for page in range(4, 40):  # NTAG213有36页可写
                write_cmd = [0xFF, 0xD6, 0x00, page, 0x04] + empty_page
                try:
                    response, sw1, sw2 = connection.transmit(write_cmd)
                    if sw1 != 0x90:
                        self.status_changed.emit(f"清空页面{page}失败: {hex(sw1)}")
                    time.sleep(0.002)
                except Exception as e:
                    self.status_changed.emit(f"清空页面{page}时出错: {str(e)}")

            # 写入数据
            self.status_changed.emit("正在写入URL数据...")
            start_page = 4
            for i in range(0, len(ndef_data), 4):
                chunk = ndef_data[i:i+4]
                if len(chunk) < 4:
                    chunk = chunk + [0x00] * (4 - len(chunk))
                
                write_cmd = [0xFF, 0xD6, 0x00, start_page + (i // 4), 0x04] + chunk
                response, sw1, sw2 = connection.transmit(write_cmd)
                if sw1 != 0x90:
                    self.status_changed.emit(f"写入页 {start_page + (i // 4)} 失败")
                    return False
                time.sleep(0.02)

            # 验证写入
            self.status_changed.emit("正在验证写入...")
            read_data = []
            for page in range(4, start_page + (len(ndef_data) // 4) + 1):
                read_cmd = [0xFF, 0xB0, 0x00, page, 0x04]
                try:
                    response, sw1, sw2 = connection.transmit(read_cmd)
                    if sw1 == 0x90:
                        read_data.extend(response)
                    else:
                        self.status_changed.emit(f"读取页面{page}失败: {hex(sw1)}")
                        return False
                    time.sleep(0.002)
                except Exception as e:
                    self.status_changed.emit(f"读取页面{page}时出错: {str(e)}")
                    return False

            # 验证数据
            if read_data[:len(ndef_data)] == ndef_data:
                self.status_changed.emit(f"NTAG213写入完成，URL长度: {len(url_bytes)}字节")
                return True
            else:
                self.status_changed.emit("数据验证失败，写入与读取不匹配")
                return False

        except Exception as e:
            self.status_changed.emit(f"NTAG213写入异常: {str(e)}")
            return False

    def write_fm08(self, connection) -> bool:
        try:
            # 使用默认密钥
            DEFAULT_KEY = [0xFF] * 6
            
            # 扇区1的密钥和访问控制
            SECTOR1_KEY_A = [0xD3, 0xF7, 0xD3, 0xF7, 0xD3, 0xF7]
            SECTOR1_ACCESS_BITS = [0x7F, 0x07, 0x88, 0x40]
            SECTOR1_KEY_B = [0xFF] * 6
            SECTOR1_TRAILER = SECTOR1_KEY_A + SECTOR1_ACCESS_BITS + SECTOR1_KEY_B

            # 1. 加载默认密钥
            load_key_cmd = [0xFF, 0x82, 0x00, 0x00, 0x06] + DEFAULT_KEY
            response, sw1, sw2 = connection.transmit(load_key_cmd)
            if sw1 != 0x90:
                self.status_changed.emit("加载密钥失败")
                return False
            time.sleep(0.1)

            # 2. 写入扇区0的块1和2
            for block in [1, 2]:
                auth_cmd = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, block, 0x60, 0x00]
                response, sw1, sw2 = connection.transmit(auth_cmd)
                if sw1 != 0x90:
                    self.status_changed.emit(f"认证块{block}失败")
                    return False

                block_data = [0x14, 0x01, 0x03, 0xE1] * 4 if block == 1 else [0x03, 0xE1] * 8
                write_cmd = [0xFF, 0xD6, 0x00, block, 0x10] + block_data
                response, sw1, sw2 = connection.transmit(write_cmd)
                if sw1 != 0x90:
                    self.status_changed.emit(f"写入块{block}失败")
                    return False
                time.sleep(0.1)

            # 3. 写入扇区1控制块
            self.status_changed.emit("写入扇区1控制块...")
            auth_cmd = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, 7, 0x60, 0x00]
            response, sw1, sw2 = connection.transmit(auth_cmd)
            if sw1 != 0x90:
                self.status_changed.emit("认证扇区1控制块失败")
                return False
            
            write_cmd = [0xFF, 0xD6, 0x00, 7, 0x10] + SECTOR1_TRAILER
            response, sw1, sw2 = connection.transmit(write_cmd)
            if sw1 != 0x90:
                self.status_changed.emit("写入扇区1控制块失败")
                return False
            
            time.sleep(0.5)

            # 4. 加载新密钥并写入扇区1数据块
            load_key_cmd = [0xFF, 0x82, 0x00, 0x00, 0x06] + SECTOR1_KEY_A
            response, sw1, sw2 = connection.transmit(load_key_cmd)
            if sw1 != 0x90:
                self.status_changed.emit("加载扇区1密钥失败")
                return False

            # 准备URL数据
            url = self.current_url
            if url.startswith("https://"):
                url = url[8:]  # 移除 https://
            url_bytes = list(url.encode('utf-8'))
            total_length = len(url_bytes) + 5  # URL长度 + NDEF头部长度

            # 写入扇区1的数据块
            for block in [4, 5, 6]:
                auth_cmd = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, block, 0x60, 0x00]
                response, sw1, sw2 = connection.transmit(auth_cmd)
                if sw1 != 0x90:
                    self.status_changed.emit(f"认证块{block}失败")
                    return False

                if block == 4:
                    # Block 4: NDEF头部 + URL开始部分
                    block_data = [
                        0x03,  # NDEF Message Start
                        total_length,  # 总长度
                        0xD1,  # NDEF Record Header
                        0x01,  # Type Length
                        len(url_bytes) + 1,  # Payload Length
                        0x55,  # Type: 'U'
                        0x04,  # URL Prefix: "https://"
                    ] + url_bytes[:9]  # URL前9个字节
                    block_data = block_data + [0x00] * (16 - len(block_data))
                elif block == 5 and len(url_bytes) > 9:
                    # Block 5: URL中间部分
                    remaining = url_bytes[9:25]  # 最多16个字节
                    block_data = remaining + [0x00] * (16 - len(remaining))
                elif block == 6 and len(url_bytes) > 25:
                    # Block 6: URL结尾部分 + 结束标记
                    remaining = url_bytes[25:]
                    block_data = remaining + [0xFE] + [0x00] * (16 - len(remaining) - 1)
                else:
                    block_data = [0x00] * 16

                write_cmd = [0xFF, 0xD6, 0x00, block, 0x10] + block_data
                response, sw1, sw2 = connection.transmit(write_cmd)
                if sw1 != 0x90:
                    self.status_changed.emit(f"写入块{block}失败")
                    return False
                time.sleep(0.1)

            self.status_changed.emit(f"FM08写入完成，URL长度: {len(url_bytes)}字节")
            return True

        except Exception as e:
            self.status_changed.emit(f"FM08写入异常: {str(e)}")
            return False

    def create_url_record(self, url_bytes: bytes) -> list:
        try:
            record_header = [
                0xD1,
                0x01,
                len(url_bytes) + 1
            ]
            record_type = [0x55]
            url_prefix = [0x01]
            url_data = list(url_bytes)
            ndef_record = record_header + record_type + url_prefix + url_data
            
            self.status_changed.emit(f"NDEF记录创建成功，长度: {len(ndef_record)}字节")
            return ndef_record
            
        except Exception as e:
            self.status_changed.emit(f"创建NDEF记录失败: {str(e)}")
            return []