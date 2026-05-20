"""烧录卡二维码生成。

每烧好一张 NFC 卡，生成一张可打印的二维码图片，供贴在卡片 / 包装上。
用户用手机扫码即可把卡绑定（认领）到自己的家庭。

二维码内容：认领链接 `{CLAIM_URL_BASE}?uid={uid}`。
二维码下方附 UID 文字便于人工核对。

两种用法：
  - render_card_qr(uid)   → 返回 PNG 字节（内存，不落盘）。卡片查询/检测只显示用。
  - generate_card_qr(uid) → 生成并保存到 ./qrcodes/{uid}.png。仅烧录成功时调用。

依赖 qrcode[pil]；未安装时静默返回 None，不影响烧录主流程。
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

try:
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
    _QR_AVAILABLE = True
except ImportError:
    _QR_AVAILABLE = False

# 认领链接前缀（用户扫码后 App / 网页据此识别卡片）
CLAIM_URL_BASE = "https://nurafamily.com/claim"

# 二维码图片输出目录（仅 generate_card_qr 落盘用）
QR_DIR = Path("./qrcodes")


def qr_available() -> bool:
    """qrcode 依赖是否就绪。"""
    return _QR_AVAILABLE


def get_qr_dir() -> Path:
    """返回二维码输出目录（不存在则创建）。"""
    QR_DIR.mkdir(parents=True, exist_ok=True)
    return QR_DIR


def _build_qr_image(uid: str, claim_url_base: str):
    """构造二维码 PIL 图像（含底部 UID 文字）。失败 / 依赖缺失返回 None。"""
    if not _QR_AVAILABLE or not uid:
        return None
    try:
        data = f"{claim_url_base}?uid={uid}"
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        # 底部留白写 UID 文字，方便工厂人工核对
        qr_w, qr_h = qr_img.size
        text_h = 40
        canvas = Image.new("RGB", (qr_w, qr_h + text_h), "white")
        canvas.paste(qr_img, (0, 0))

        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("Arial.ttf", 18)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), uid, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text(((qr_w - text_w) / 2, qr_h + 8), uid, fill="black", font=font)
        return canvas
    except Exception as e:
        print(f"[qr_export] 构造二维码失败 uid={uid}: {e}")
        return None


def render_card_qr(uid: str, claim_url_base: str = CLAIM_URL_BASE) -> bytes | None:
    """生成认领二维码 PNG 字节（内存，不落盘）。失败返回 None。

    卡片查询 / 检测窗口用 —— 只为屏幕显示，不往 qrcodes/ 堆文件。
    """
    img = _build_qr_image(uid, claim_url_base)
    if img is None:
        return None
    try:
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"[qr_export] 渲染二维码失败 uid={uid}: {e}")
        return None


def generate_card_qr(uid: str, claim_url_base: str = CLAIM_URL_BASE) -> str | None:
    """生成认领二维码 PNG 并保存到 ./qrcodes/{uid}.png。

    仅在烧录成功时调用 —— 每张烧好的卡留一份二维码文件。
    返回保存路径；依赖缺失 / uid 为空 / 失败时返回 None。
    """
    data = render_card_qr(uid, claim_url_base)
    if data is None:
        return None
    try:
        out_dir = get_qr_dir()
        path = out_dir / f"{uid}.png"
        with open(path, "wb") as f:
            f.write(data)
        return str(path)
    except Exception as e:
        print(f"[qr_export] 保存二维码失败 uid={uid}: {e}")
        return None
