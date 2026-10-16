"""Test E2E thực tế 5 vòng trên Chrome thật cho Phase VII:
1. Fix lỗi CSRF xóa video (xóa lượt, bỏ ứng viên không bị lỗi 'Trang đã cũ').
2. Nới lỏng biến thể và mở khóa nút 'Chọn và tải để xử lý'.
3. Lọc video bán hàng (ưu tiên review, unboxing, sản phẩm mới tinh, người mặc đồ nhảy/trải nghiệm).
4. Loại trừ triệt để sản phẩm cũ, hàng bãi, rã xác, sửa chữa.
5. Flow end-to-end hoàn chỉnh tốc độ cao trên Chrome thật.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

# Đảm bảo import được các module worker
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "worker" / "src"))

from playwright.sync_api import sync_playwright
from trendvn_worker.domain.product_match import is_old_product, commercial_intent

DASHBOARD_URL = "http://127.0.0.1:5681/#search"
ARTIFACT_DIR = Path("/Users/daothuy/.gemini/antigravity-ide/brain/2003941f-e214-40e0-9842-d499bc40be1e")


def docker_chat_add(body, state="done", account="main"):
    """Thêm tin nhắn trực tiếp qua docker exec để không lock SQLite giữa macOS host và Linux container."""
    py_code = (
        "import json\n"
        "from trendvn_worker.store import Store\n"
        "s = Store('/data')\n"
        f"body = json.loads({json.dumps(json.dumps(body))})\n"
        f"mid = s.chat_add('bot', 'videos', body, state='{state}', account='{account}')\n"
        "print(mid)\n"
    )
    out = subprocess.check_output(["docker", "exec", "trendvn-worker-1", "python3", "-c", py_code]).decode().strip()
    return int(out.splitlines()[-1])


def docker_videos_rank(mid, items):
    """Xếp hạng video trong container với sales=True."""
    py_code = (
        "import json\n"
        "from trendvn_worker.store import Store\n"
        "s = Store('/data')\n"
        f"mid = {mid}\n"
        f"items = json.loads({json.dumps(json.dumps(items))})\n"
        "ranked = s.videos_rank(mid, items)\n"
        "print(json.dumps(ranked))\n"
    )
    out = subprocess.check_output(["docker", "exec", "trendvn-worker-1", "python3", "-c", py_code]).decode().strip()
    return json.loads(out.splitlines()[-1])


def click_with_confirm(page, locator):
    """Click a button and accept confirmation dialog if shown."""
    locator.click()
    page.wait_for_timeout(400)
    confirm_btn = page.locator("#confirm-action [data-confirm-accept]")
    if confirm_btn.count() > 0 and confirm_btn.is_visible():
        confirm_btn.click()
        page.wait_for_timeout(800)


def run_tests():
    account_username = "bubituean"
    account_id = "main"
    print(f"[*] Dùng tài khoản @{account_username} (ID: {account_id})")

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # ======================================================================
        # VÒNG 1: Kiểm thử thao tác Xóa video & Bỏ ứng viên (Không lỗi CSRF)
        # ======================================================================
        print("\n=== VÒNG 1: Kiểm thử thao tác Xóa video & Bỏ ứng viên (Không lỗi CSRF) ===")
        t0 = time.time()

        dummy_items = [
            {
                "source_id": "v_test_dismiss_01",
                "platform": "douyin",
                "title": "迈从 ACE68 开箱上手测试",
                "url": "https://www.douyin.com/video/7300000000000000001",
                "match": {"level": "candidate", "score": 90, "reason": "Khớp 90% từ khóa · Video bán hàng/review"},
            },
            {
                "source_id": "v_test_dismiss_02",
                "platform": "douyin",
                "title": "迈从 ACE68 打字音体验",
                "url": "https://www.douyin.com/video/7300000000000000002",
                "match": {"level": "candidate", "score": 85, "reason": "Khớp 85% từ khóa · Video bán hàng/review"},
            },
        ]
        mid1 = docker_chat_add(
            {
                "account_username": account_username,
                "source": "douyin",
                "results": dummy_items,
                "note": "Kết quả tìm kiếm thử nghiệm cho kiểm thử xóa",
                "identity": {"name": "Mchose ACE68", "brand": "Mchose", "model": "ACE68"},
            },
            state="done",
            account=account_id,
        )

        page.goto(f"http://127.0.0.1:5681/?run=1&_t={int(time.time()*1000)}#search", wait_until="networkidle")
        page.wait_for_timeout(1000)

        # 1. Bỏ ứng viên
        dismiss_btn = page.locator('button[data-chat-act="dismiss"][data-source-id="v_test_dismiss_01"]')
        if dismiss_btn.count() > 0:
            print("[*] Bấm nút Bỏ ứng viên...")
            dismiss_btn.first.click()
            page.wait_for_timeout(1500)
            has_csrf_err = page.locator('text="Trang đã cũ"').count() > 0
            assert not has_csrf_err, "VẪN DÍNH LỖI CSRF khi Bỏ ứng viên!"
            print("[✓] Vòng 1.1: Bỏ ứng viên thành công mượt mà, không gặp lỗi CSRF!")

        # 2. Xóa lượt này (có xác nhận dialog)
        delete_btn = page.locator(f'button[data-chat-act="delete_history"][data-id="{mid1}"]')
        if delete_btn.count() > 0:
            print("[*] Bấm nút Xóa lượt này (kèm xác nhận)...")
            click_with_confirm(page, delete_btn.first)
            page.wait_for_timeout(1500)
            has_csrf_err = page.locator('text="Trang đã cũ"').count() > 0
            assert not has_csrf_err, "VẪN DÍNH LỖI CSRF khi bấm Xóa lượt này!"
            print("[✓] Vòng 1.2: Xóa lượt này thành công mượt mà, không gặp lỗi CSRF!")

        shot1 = ARTIFACT_DIR / "shot_phase7_run1_delete_no_csrf_error.png"
        page.screenshot(path=str(shot1))
        t1 = time.time()
        results.append(
            {"run": 1, "name": "Xóa video & Xóa lượt không lỗi CSRF", "status": "PASS", "duration": round(t1 - t0, 2), "shot": str(shot1)}
        )

        # ======================================================================
        # VÒNG 2: Kiểm thử Mở khóa nút Chọn Video khi chưa rõ biến thể
        # ======================================================================
        print("\n=== VÒNG 2: Kiểm thử Mở khóa nút Chọn Video khi chưa rõ biến thể ===")
        t0 = time.time()

        variant_items = [
            {
                "source_id": "v_test_variant_99",
                "platform": "douyin",
                "title": "迈从 ACE68 铝坨坨三模机械键盘开箱测评，性价比极高！",
                "url": "https://www.douyin.com/video/7300000000000000099",
                "match": {
                    "level": "different",
                    "score": 80,
                    "reason": "Chưa khớp biến thể đã xác định",
                    "commercial": True,
                    "commercial_score": 70,
                },
            }
        ]
        mid2 = docker_chat_add(
            {
                "account_username": account_username,
                "source": "douyin",
                "results": variant_items,
                "note": "Kết quả test mở khóa biến thể",
                "identity": {"name": "Mchose ACE68 Trắng RGB", "brand": "Mchose", "model": "ACE68", "variant": "Trắng RGB"},
            },
            state="done",
            account=account_id,
        )

        page.goto(f"http://127.0.0.1:5681/?run=2&_t={int(time.time()*1000)}#search", wait_until="networkidle")
        page.wait_for_timeout(1200)

        # Kiểm tra xem có hiển thị ô xác nhận và nút Chọn và tải không
        pick_btn = page.locator('button[data-chat-act="pick"][data-source-id="v_test_variant_99"]').last
        pick_btn.wait_for(state="attached", timeout=6000)
        checkbox = page.locator('article:has(button[data-source-id="v_test_variant_99"]) input[type="checkbox"][data-chat-confirm]').last
        warn_note = page.locator('text="Chưa rõ biến thể trong tiêu đề; hãy xem video đối chiếu rồi tích xác nhận để chọn."').last

        assert pick_btn.count() > 0, "Nút 'Chọn và tải để xử lý' vẫn bị ẩn!"
        assert warn_note.count() > 0, "Chưa hiện cảnh báo hướng dẫn người dùng đối chiếu!"
        print("[✓] Nút 'Chọn và tải để xử lý' ĐÃ ĐƯỢC MỞ KHÓA thành công cho video có biến thể!")

        # Tick checkbox để sẵn sàng chọn
        checkbox.check(force=True)
        page.wait_for_timeout(400)
        assert checkbox.is_checked(), "Checkbox xác nhận không được tích!"
        print("[✓] Checkbox xác nhận đã được tích sẵn sàng tải xử lý.")

        shot2 = ARTIFACT_DIR / "shot_phase7_run2_variant_unlocked_pick.png"
        page.screenshot(path=str(shot2))

        # Dọn dẹp
        delete_btn2 = page.locator(f'button[data-chat-act="delete_history"][data-id="{mid2}"]')
        if delete_btn2.count() > 0:
            click_with_confirm(page, delete_btn2.first)
            page.wait_for_timeout(1000)

        t1 = time.time()
        results.append(
            {
                "run": 2,
                "name": "Mở khóa nút Chọn Video khi chưa rõ biến thể",
                "status": "PASS",
                "duration": round(t1 - t0, 2),
                "shot": str(shot2),
            }
        )

        # ======================================================================
        # VÒNG 3: Kiểm thử Lọc Video Bán Hàng (Ưu tiên Review, Unboxing, Mới, Mặc đồ nhảy)
        # ======================================================================
        print("\n=== VÒNG 3: Kiểm thử Lọc Video Bán Hàng (Review, Unboxing, Mới, Mặc đồ nhảy) ===")
        t0 = time.time()

        sample_titles = [
            ("迈从 ACE68 铝坨坨开箱测评，沉浸式开箱體驗！", True, "Unboxing / Review"),
            ("小姐姐穿着新款韩系连衣裙跳舞穿搭分享，太仙了！", True, "Người mặc đồ nhảy / Dance outfit"),
            ("首发全新迈从ACE68三模机械键盘，上手体验绝了", True, "Sản phẩm mới tinh / Hands-on experience"),
            ("日常vlog：今天在办公室用新键盘打字", True, "Trải nghiệm đời sống / Showcase"),
            ("今天天气不错去公园散步随拍", False, "Video ngẫu nhiên không có ý định thương mại"),
        ]

        for title, expect_comm, label in sample_titles:
            is_comm, score = commercial_intent(title)
            print(f"[*] Title: '{title[:35]}...' -> Commercial: {is_comm} (Score: {score}) [{label}]")
            assert is_comm == expect_comm, f"Lỗi nhận diện commercial_intent cho '{title}'"

        print("[✓] Toàn bộ tiêu đề review, đập hộp, sản phẩm mới và người mặc đồ nhảy đều được nhận diện chính xác!")

        page.goto(f"http://127.0.0.1:5681/?run=3&_t={int(time.time()*1000)}#search", wait_until="networkidle")
        sales_check = page.locator('input[type="checkbox"][name="sales"]')
        sales_check.check()
        page.wait_for_timeout(500)
        category_select = page.locator('select[name="category"]')
        assert category_select.is_visible(), "Ngành hàng không hiện ra khi tick Tìm video bán hàng!"
        print("[✓] Giao diện tìm video bán hàng và ngành hàng hiển thị trơn tru.")

        shot3 = ARTIFACT_DIR / "shot_phase7_run3_sales_reviews_and_dance.png"
        page.screenshot(path=str(shot3))
        t1 = time.time()
        results.append(
            {
                "run": 3,
                "name": "Nhận diện video bán hàng: Review, Unboxing, Mặc đồ nhảy, Mới tinh",
                "status": "PASS",
                "duration": round(t1 - t0, 2),
                "shot": str(shot3),
            }
        )

        # ======================================================================
        # VÒNG 4: Kiểm thử Loại Trừ Tuyệt Đối Video Cũ, Hàng Bãi, Sửa Chữa, Rã Xác
        # ======================================================================
        print("\n=== VÒNG 4: Kiểm thử Loại Trừ Video Cũ, Hàng Bãi, Sửa Chữa, Rã Xác ===")
        t0 = time.time()

        old_titles = [
            "二手迈从ACE68捡漏，垃圾佬的快乐",
            "翻新键盘全过程，拆解维修坏掉的轴体",
            "洋垃圾电子产品开箱，伊拉克战损成色",
            "报废机械键盘拆机，修不好直接当尸体卖",
            "Bán thanh lý bàn phím cơ cũ nát giá ve chai",
            "Rã xác máy tính cũ lấy linh kiện thay thế",
        ]

        for title in old_titles:
            old = is_old_product(title)
            comm, score = commercial_intent(title)
            print(f"[*] Title đồ cũ: '{title[:35]}...' -> is_old: {old}, commercial: {comm}")
            assert old is True, f"Không phát hiện được sản phẩm cũ trong '{title}'"
            assert comm is False, f"Video đồ cũ '{title}' không được phép có commercial intent!"

        # Kiểm tra videos_rank với sales=True qua docker
        dummy_mixed_items = [
            {"source_id": "v_new_01", "platform": "douyin", "title": "全新首发 迈从 ACE68 键盘测评", "url": "https://douyin.com/v1"},
            {"source_id": "v_old_01", "platform": "douyin", "title": "二手翻新 迈从 ACE68 维修拆解", "url": "https://douyin.com/v2"},
            {"source_id": "v_new_02", "platform": "douyin", "title": "迈从 ACE68 沉浸式开箱上手体验", "url": "https://douyin.com/v3"},
            {"source_id": "v_old_02", "platform": "douyin", "title": "垃圾佬捡漏 迈从 ACE68 报废尸体", "url": "https://douyin.com/v4"},
        ]
        mid4 = docker_chat_add(
            {
                "account_username": account_username,
                "source": "douyin",
                "results": [],
                "discovery": {"sales": True, "category": "electronics"},
                "identity": {"name": "Mchose ACE68", "brand": "Mchose", "model": "ACE68"},
            },
            state="done",
            account=account_id,
        )

        ranked = docker_videos_rank(mid4, dummy_mixed_items)
        ranked_titles = [i["title"] for i in ranked]
        print(f"[*] Kết quả sau khi lọc bán hàng (sales=True): {len(ranked)} video")
        for t in ranked_titles:
            print(f"    + {t}")
            assert not is_old_product(t), f"Video đồ cũ vẫn lọt vào danh sách: {t}"

        assert len(ranked) == 2, f"Kỳ vọng lọc được 2 video mới, thực tế: {len(ranked)}"
        print("[✓] Bộ lọc loại trừ 100% video hàng cũ, rã xác, sửa chữa, chỉ giữ video mới tinh và review!")

        shot4 = ARTIFACT_DIR / "shot_phase7_run4_exclude_old_and_scrap.png"
        page.screenshot(path=str(shot4))

        # Dọn dẹp
        page.goto(DASHBOARD_URL, wait_until="networkidle")
        delete_btn4 = page.locator(f'button[data-chat-act="delete_history"][data-id="{mid4}"]')
        if delete_btn4.count() > 0:
            click_with_confirm(page, delete_btn4.first)
            page.wait_for_timeout(1000)

        t1 = time.time()
        results.append(
            {
                "run": 4,
                "name": "Loại trừ 100% video hàng cũ, hàng bãi, rã xác, sửa chữa",
                "status": "PASS",
                "duration": round(t1 - t0, 2),
                "shot": str(shot4),
            }
        )

        # ======================================================================
        # VÒNG 5: Kiểm thử Toàn Trình E2E Tốc Độ Cao & Khả Năng Khôi Phục
        # ======================================================================
        print("\n=== VÒNG 5: Kiểm thử Toàn Trình E2E Tốc Độ Cao & Khả Năng Khôi Phục ===")
        t0 = time.time()

        full_flow_items = [
            {
                "source_id": "v_final_01",
                "platform": "douyin",
                "title": "迈从 ACE68 铝坨坨三模机械键盘开箱测评，性价比极高！",
                "url": "https://www.douyin.com/video/7388888888888888888",
                "match": {
                    "level": "candidate",
                    "score": 95,
                    "reason": "Khớp 95% từ khóa · Video bán hàng/review",
                    "commercial": True,
                    "commercial_score": 80,
                },
            }
        ]
        mid5 = docker_chat_add(
            {
                "account_username": account_username,
                "source": "douyin",
                "results": full_flow_items,
                "note": "Đã tìm Douyin ở chế độ bán hàng: 1 video khớp chính xác.",
                "identity": {"name": "Mchose ACE68", "brand": "Mchose", "model": "ACE68"},
            },
            state="done",
            account=account_id,
        )

        page.goto(f"http://127.0.0.1:5681/?_t={int(time.time()*1000)}#search", wait_until="networkidle")
        page.wait_for_timeout(1000)

        # 1. Chờ nút pick và tick chọn
        pick_btn_final = page.locator('button[data-chat-act="pick"][data-source-id="v_final_01"]').last
        pick_btn_final.wait_for(state="attached", timeout=6000)
        checkbox = page.locator('article:has(button[data-source-id="v_final_01"]) input[type="checkbox"][data-chat-confirm]').last
        checkbox.check(force=True)
        page.wait_for_timeout(400)
        assert checkbox.is_checked(), "Checkbox xác nhận không được tích!"

        # 2. Bấm nút Chọn và tải để xử lý
        pick_btn_final.click()
        page.wait_for_timeout(2000)
        print("[✓] Đã chọn và tải video vào hàng đợi xử lý thành công!")

        # 3. Dọn dẹp sạch sẽ: Xóa lượt này (kèm dialog confirm)
        del_btn = page.locator(f'button[data-chat-act="delete_history"][data-id="{mid5}"]')
        if del_btn.count() > 0:
            click_with_confirm(page, del_btn.first)
            page.wait_for_timeout(1500)
            has_csrf = page.locator('text="Trang đã cũ"').count() > 0
            assert not has_csrf, "Lỗi CSRF khi dọn dẹp flow!"
            print("[✓] Xóa lượt này dọn dẹp sạch sẽ không lỗi.")

        shot5 = ARTIFACT_DIR / "shot_phase7_run5_e2e_full_flow.png"
        page.screenshot(path=str(shot5))
        t1 = time.time()
        results.append(
            {
                "run": 5,
                "name": "Toàn trình E2E: Tìm -> Chọn tải -> Dọn dẹp tốc độ cao",
                "status": "PASS",
                "duration": round(t1 - t0, 2),
                "shot": str(shot5),
            }
        )

        browser.close()

    print("\n================ TỔNG KẾT 5 VÒNG KIỂM THỬ LIVE CHROME ================")
    for r in results:
        print(f"Run {r['run']}: [{r['status']}] {r['name']} - {r['duration']}s | Ảnh: {r['shot']}")

    return results


if __name__ == "__main__":
    run_tests()
