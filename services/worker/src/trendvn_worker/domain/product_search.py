"""Bounded search inputs (text, files, links): validation only, no network or database access."""

import base64
import binascii
import io
import zipfile
from pathlib import PurePath
from xml.etree import ElementTree

MAX_FILE = 4 << 20
MAX_TOTAL = 8 << 20
MAX_FILES = 3
MAX_TEXT = 12000
MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".pdf": "application/pdf"}


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
