"""Bounded search inputs and conservative product identity matching; no network or database access."""

import base64
import binascii
import io
import re
import unicodedata
import zipfile
from pathlib import PurePath
from urllib.parse import urlsplit
from xml.etree import ElementTree

from .search_queries import normalized

MAX_FILE = 4 << 20
MAX_TOTAL = 8 << 20
MAX_FILES = 3
MAX_TEXT = 12000
MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".pdf": "application/pdf"}


def public_url(value):
    if not isinstance(value, str) or len(value) > 2000 or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        raise ValueError("Đường dẫn không hợp lệ")
    u = urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None, 443):
        raise ValueError("Chỉ nhận đường dẫn HTTPS công khai")
    return value


def _document(data, ext):
    if ext == ".txt":
        try:
            return data.decode("utf-8-sig")[:MAX_TEXT]
        except UnicodeError:
            raise ValueError("Tệp TXT cần dùng UTF-8") from None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entries = z.infolist()
            if len(entries) > 200 or sum(i.file_size for i in entries) > 16 << 20 or any(i.flag_bits & 1 for i in entries):
                raise ValueError("DOCX quá lớn hoặc được mã hóa")
            info = z.getinfo("word/document.xml")
            if info.file_size > 2 << 20:
                raise ValueError("Văn bản DOCX quá lớn")
            raw = z.read(info)
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise ValueError("DOCX chứa cấu trúc XML không được hỗ trợ")
            root = ElementTree.fromstring(raw)
            return " ".join(n.text or "" for n in root.iter() if n.tag.endswith("}t"))[:MAX_TEXT]
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        raise ValueError("Tệp DOCX không hợp lệ") from None


def attachment(value):
    if not isinstance(value, dict) or not isinstance(value.get("name"), str) or not isinstance(value.get("data"), str):
        raise ValueError("Tệp đính kèm không hợp lệ")
    name = value["name"]
    if len(name) > 180 or PurePath(name).name != name or "\\" in name:
        raise ValueError("Tên tệp không hợp lệ")
    if len(value["data"]) > ((MAX_FILE + 2) // 3) * 4:
        raise ValueError("Mỗi tệp tối đa 4 MiB")
    try:
        raw = base64.b64decode(value["data"], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Dữ liệu tệp không hợp lệ") from None
    if not 0 < len(raw) <= MAX_FILE:
        raise ValueError("Tệp rỗng hoặc vượt 4 MiB")
    ext = PurePath(name).suffix.lower()
    if ext in (".txt", ".docx"):
        return {"name": name, "text": _document(raw, ext), "size": len(raw)}
    signatures = {
        ".png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": raw.startswith(b"\xff\xd8\xff"),
        ".jpeg": raw.startswith(b"\xff\xd8\xff"),
        ".webp": raw[:4] == b"RIFF" and raw[8:12] == b"WEBP",
        ".pdf": raw.startswith(b"%PDF-"),
    }
    if not signatures.get(ext):
        raise ValueError("Chỉ nhận ảnh PNG/JPEG/WebP, PDF, DOCX hoặc TXT đúng định dạng")
    return {"name": name, "mime": MIMES[ext], "data": value["data"], "size": len(raw)}


def validate_input(payload):
    if not isinstance(payload, dict):
        raise ValueError("Yêu cầu tìm kiếm không hợp lệ")
    text, files = payload.get("text", ""), payload.get("files", [])
    if not isinstance(text, str) or len(text) > MAX_TEXT or not isinstance(files, list) or len(files) > MAX_FILES:
        raise ValueError("Tối đa 12.000 ký tự và 3 tệp")
    files = [attachment(f) for f in files]
    if sum(f["size"] for f in files) > MAX_TOTAL:
        raise ValueError("Tổng tệp tối đa 8 MiB")
    return {"text": text.strip(), "files": files}


def tokens(text):
    text = unicodedata.normalize("NFKD", normalized(text).replace("đ", "d"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", text))


def match_identity(identity, title, product_id=""):
    """Labels are evidence, never a probability. A model mismatch excludes a result even when most keywords overlap."""
    expected = str(identity.get("product_id") or "")
    if expected and product_id:
        return {
            "level": "id" if expected == product_id else "different",
            "score": 100 if expected == product_id else 0,
            "reason": "Cùng mã sản phẩm" if expected == product_id else "Khác mã sản phẩm",
        }
    wanted, seen = tokens(identity.get("name") or identity.get("query", "")), tokens(title)
    model = tokens(identity.get("model", ""))
    model |= {t for t in wanted if any(c.isdigit() for c in t)}
    brand, variant = tokens(identity.get("brand", "")), tokens(identity.get("variant", ""))
    if brand and not brand <= seen:
        return {"level": "different", "score": 0, "reason": "Chưa khớp thương hiệu đã xác định"}
    if variant and not variant <= seen:
        return {"level": "different", "score": 0, "reason": "Chưa khớp biến thể đã xác định"}
    extras = {"ultra", "pro", "max", "plus", "mini", "lite", "fe", "air", "turbo", "gt", "v2"}
    version = re.findall(r"\bv\s*(\d+)\b", normalized(title))
    wanted_version = re.findall(r"\bv\s*(\d+)\b", normalized(identity.get("name") or identity.get("query", "")))
    if model and ((seen & extras) - wanted - variant or set(version) - set(wanted_version)):
        return {"level": "different", "score": 0, "reason": "Có biến thể khác với sản phẩm yêu cầu"}
    if model and not model <= seen:
        return {"level": "different", "score": 0, "reason": "Chưa khớp model; không coi là đúng sản phẩm"}
    if brand and model:
        wanted = brand | model | variant
    if not wanted:
        return {"level": "unverified", "score": 0, "reason": "Chưa có thông tin đối chiếu"}
    score = round(100 * len(wanted & seen) / len(wanted))
    return {"level": "candidate", "score": score, "reason": "Khớp %d%% từ khóa; cần xem video và biến thể" % score}
