"""Official shoppable video submission with a dry-run and conservative outcome handling after the publish request."""

import hashlib
import re
import secrets
import time

from .catalog import context, showcase_products

UPLOAD_LIMIT = 10 << 20  # documented single-upload limit; larger videos stay parked, never silently lose their basket


def _upload(client, video):
    if video.stat().st_size > UPLOAD_LIMIT:
        raise ValueError("Video vượt 10 MiB của API tải trực tiếp TikTok Shop; cần luồng tải tệp lớn, chưa đăng")
    boundary = "trendvn-" + secrets.token_hex(16)
    content = video.read_bytes()
    body = (
        '--%s\r\nContent-Disposition: form-data; name="data"; filename="video.mp4"\r\nContent-Type: video/mp4\r\n\r\n' % boundary
    ).encode()
    body += content + ("\r\n--%s--\r\n" % boundary).encode()
    data = client.request("/affiliate_creator/202505/videos/video_files", multipart=("multipart/form-data; boundary=" + boundary, body))
    result = data.get("video_file") or {}
    fid, digest = result.get("id"), result.get("md5")
    if not isinstance(fid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", fid):
        raise ValueError("TikTok Shop chưa xác nhận tệp video tải lên")
    if not isinstance(digest, str) or digest.casefold() != hashlib.md5(content).hexdigest():
        raise ValueError("Tệp TikTok Shop nhận không khớp video đã chọn; không đăng")
    return fid


def _publish(job, video, dry_run, state):
    """The caller checks the local output hash. Before submission errors are deferred; after submission they are always unknown."""
    account, client, _ = context(job["account"])
    if account.get("username", "").casefold() != job["target"].casefold():
        return "deferred", "", "Tài khoản đã thay đổi sau khi chọn đăng; dừng trước lệnh đăng"
    scopes = client.credentials.get("granted_scopes")
    if isinstance(scopes, list) and "creator.video.write" not in scopes:
        return "deferred", "", "Chưa cấp quyền đăng video kèm sản phẩm; cần cấp thêm quyền trong kết nối nhà sáng tạo"
    product = next((p for p in showcase_products(client) if p["product_id"] == job["product"]["product_id"]), None)
    if not product or not product["can_attach"]:
        return "deferred", "", "Sản phẩm đã hết hàng, mất hoa hồng hoặc không còn trong showcase của tài khoản; không đăng"
    if job.get("visibility", "public") != "public":
        return "deferred", "", "API video kèm sản phẩm hiện chỉ hỗ trợ đăng công khai trong hệ thống; chưa đăng để giữ đúng chế độ bạn chọn"
    file_id = _upload(client, video)
    if dry_run:
        return (
            "dry_run",
            "",
            "Chạy thử API: đúng tài khoản, sản phẩm còn hoa hồng/trong showcase, video tải lên khớp MD5; chưa gửi lệnh Đăng",
        )
    title = re.sub(r"[^\w\s]", "", product["title"])[:30].strip()
    if not title:
        return "deferred", "", "Tên nhãn sản phẩm không hợp lệ; chưa đăng"
    body = {
        "video_info": {"file_id": file_id, "title": job["caption"]},
        "product_link_info": {"product_id": product["product_id"], "title": title},
    }
    state["clicked"] = True  # a lost HTTP response can mean a post was accepted; never submit the video a second time automatically
    result = client.request("/affiliate_creator/202603/videos", body=body)
    vid = (result.get("video") or {}).get("id")
    if not isinstance(vid, str) or not re.fullmatch(r"\d{6,25}", vid):
        return "unknown", "", "Đã gửi lệnh đăng kèm sản phẩm; TikTok chưa trả mã bài đăng, cần bạn kiểm tra"
    url = "https://www.tiktok.com/@%s/video/%s" % (job["target"], vid)
    for _ in range(4):
        data = client.request("/affiliate_creator/202509/videos/%s/status" % vid)
        status = (data.get("video") or {}).get("post_status")
        if status == "SUCCESS":
            return "published", url, "TikTok Shop API xác nhận video kèm mã sản phẩm " + product["product_id"]
        if status == "FAIL":
            return "unknown", url, "TikTok báo bài đăng không thành công; cần kiểm tra trước khi đăng lại"
        time.sleep(3)
    return "unknown", url, "TikTok đã nhận lệnh đăng nhưng chưa xác nhận hoàn tất; kiểm tra bài trước khi thử lại"


def publish(job, video, dry_run, state):
    try:
        return _publish(job, video, dry_run, state)
    except (ValueError, OSError) as error:
        if state.get("clicked"):
            return "unknown", "", "Đã gửi lệnh đăng nhưng chưa xác nhận; kiểm tra tài khoản trước khi thử lại"
        return "deferred", "", str(error)[:500]
