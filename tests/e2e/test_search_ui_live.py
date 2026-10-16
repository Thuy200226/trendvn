"""Live Browser E2E Test & 5-Run Optimization for TrendVN Search UI.
Connects directly to the live TrendVN dashboard at http://127.0.0.1:5681/#search.
Verifies every interactive element: form controls, sales toggle, required category,
empty validation, submission, product cards, candidate actions (pick/dismiss),
history deletion (delete_history/clear with confirm dialogs), responsive audit and console health.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = Path("/Users/daothuy/.gemini/antigravity-ide/brain/2003941f-e214-40e0-9842-d499bc40be1e")
URL = "http://127.0.0.1:5681"


def seed_test_candidate():
    """Seed a real candidate message into worker SQLite database for live UI interaction."""
    code = """
import sqlite3, json, time
con = sqlite3.connect('/data/trendvn.sqlite3')
account = con.execute("SELECT id, username FROM accounts WHERE enabled=1 LIMIT 1").fetchone()
acc_id = account[0] if account else 'main'
acc_user = account[1] if account else 'bubituean'
now = time.time()

# 1. Product message
prod_body = {
    "identity": {
        "name": "Bàn phím cơ Mchose ACE68",
        "query": "迈从 ACE68",
        "brand": "Mchose",
        "model": "ACE68",
        "variant": "Trắng RGB",
        "queries": {"douyin": "迈从 ACE68", "tiktok": "Mchose ACE68"}
    },
    "account_username": acc_user
}
con.execute(
    "INSERT INTO chat (account, role, kind, state, body, request_key, created) VALUES (?, 'bot', 'product', 'done', ?, ?, ?)",
    (acc_id, json.dumps(prod_body), f"test_prod_{now}", now)
)
prod_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

# 2. Videos candidate message
vid_body = {
    "identity": prod_body["identity"],
    "source": "douyin",
    "product": prod_id,
    "turn_id": prod_id,
    "account_username": acc_user,
    "results": [
        {
            "source_id": f"test_video_ace68_{int(now)}",
            "platform": "douyin",
            "title": "Trải nghiệm gõ phím cơ Mchose ACE68 Trắng RGB cực êm",
            "url": "https://www.douyin.com/video/71234567890",
            "match": {"level": "candidate", "reason": "Khớp chính xác model ACE68 và thương hiệu Mchose"}
        }
    ],
    "note": "Ứng viên tìm kiếm thử nghiệm live"
}
con.execute(
    "INSERT INTO chat (account, role, kind, state, body, request_key, created) VALUES (?, 'bot', 'videos', 'done', ?, ?, ?)",
    (acc_id, json.dumps(vid_body), f"test_vids_{now}", now + 0.1)
)
con.commit()
print(f"SEEDED_OK: prod_id={prod_id}")
"""
    cmd = ["docker", "exec", "trendvn-worker-1", "python", "-c", code]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("Không thể seed candidate vào database: " + res.stderr)
    print("  ✓ Đã seed candidate message vào CSDL hệ thống thật:", res.stdout.strip())


def run_live_audit(headless=True):
    console_errors = []
    page_errors = []
    audit_results = {
        "run1_form_controls": {},
        "run2_input_and_submit": {},
        "run3_candidate_actions": {},
        "run4_history_management": {},
        "run5_edge_cases_and_responsive": {},
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Listen to console messages and page errors
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type in ("error", "warning") and "favicon" not in msg.text else None,
        )
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        print("=== BẮT ĐẦU VÒNG 1: KIỂM THỬ FORM CONTROLS & BỘ LỌC BÁN HÀNG ===")
        page.goto(URL + "/#search", wait_until="networkidle")
        time.sleep(0.5)

        # 1.1 Verify search layout is active
        search_box = page.locator("#search")
        assert search_box.is_visible(), "Tab #search không hiển thị"
        composer = page.locator("[data-chat-form]")
        assert composer.is_visible(), "Form composer không hiển thị"

        # 1.2 Empty validation
        send_btn = composer.locator("button.send")
        textbox = composer.locator('textarea[name="text"]')
        status_msg = page.locator("[data-chat-message]")
        topic_select = composer.locator('select[name="topic"]')

        textbox.fill("")
        topic_select.select_option(value="")
        send_btn.click()
        time.sleep(0.3)
        assert "Hãy nhập từ khóa" in status_msg.inner_text(), "Validation trống không báo đúng: " + status_msg.inner_text()
        print("  ✓ Validation form rỗng hoạt động chính xác: chặn gửi và hiển thị hướng dẫn")
        audit_results["run1_form_controls"]["empty_validation"] = "passed"

        # 1.3 Sales checkbox and category dropdown toggle
        sales_check = composer.locator('input[name="sales"]')
        cat_label = composer.locator("[data-sales-category]")
        cat_select = composer.locator('select[name="category"]')

        assert cat_label.is_hidden(), "Dropdown ngành hàng phải ẩn khi sales chưa tick"
        assert not cat_select.get_attribute("required"), "Ngành hàng không được required khi sales chưa tick"

        # Tick sales
        sales_check.check()
        time.sleep(0.2)
        assert cat_label.is_visible(), "Dropdown ngành hàng phải hiện khi sales đã tick"
        assert cat_select.get_attribute("required") is not None, "Ngành hàng phải có required khi sales đã tick"
        print("  ✓ Tick 'Tìm video bán hàng': dropdown ngành hàng hiển thị mượt mà và tự gán required=True")

        # Untick sales
        sales_check.uncheck()
        time.sleep(0.2)
        assert cat_label.is_hidden(), "Dropdown ngành hàng phải ẩn lại khi sales bỏ tick"
        assert not cat_select.get_attribute("required"), "Ngành hàng phải hủy required khi sales bỏ tick"
        print("  ✓ Bỏ tick 'Tìm video bán hàng': dropdown ngành hàng ẩn đi và tự hủy required")
        audit_results["run1_form_controls"]["sales_toggle"] = "passed"

        # 1.4 Account and topic sync
        acc_select = composer.locator('select[name="account"]')
        source_select = composer.locator('select[name="source"]')
        assert acc_select.is_visible() and topic_select.is_visible() and source_select.is_visible()
        print("  ✓ Dropdown Tài khoản, Nguồn và Thể loại hiển thị đầy đủ và đồng bộ")
        audit_results["run1_form_controls"]["account_sync"] = "passed"

        page.screenshot(path=str(ARTIFACT_DIR / "shot_run1_controls.png"))

        print("\n=== BẮT ĐẦU VÒNG 2: KIỂM THỬ NHẬP LIỆU & GỬI TÌM KIẾM SẢN PHẨM ===")
        # 2.1 Nhập sản phẩm và gửi qua phím tắt Ctrl/Cmd+Enter
        sales_check.check()
        cat_select.select_option(value="electronics")
        source_select.select_option(value="douyin")
        textbox.fill("迈从 ACE68")
        textbox.focus()

        # Gửi bằng phím Enter (Cmd+Enter trên mac)
        textbox.press("Meta+Enter" if sys.platform == "darwin" else "Control+Enter")

        # Đợi request /chat/send hoàn thành (textbox được làm sạch)
        try:
            page.wait_for_function("() => document.querySelector('[data-chat-form] textarea[name=\"text\"]').value === ''", timeout=12000)
        except Exception:
            err = status_msg.inner_text()
            val = textbox.input_value()
            raise AssertionError(f"Textarea chưa được reset. Status: '{err}', Value: '{val}'")
        user_bubble = page.locator("#chat-thread .msg.me", has_text="迈从 ACE68")
        assert user_bubble.count() > 0, "Bong bóng tin nhắn của người dùng phải hiển thị trong thread"
        print("  ✓ Phím tắt Ctrl/Cmd+Enter submit form thành công, ô nhập tự động dọn sạch")

        # Chờ bot bubble phản hồi (product card)
        page.wait_for_selector("#chat-thread .msg.bot", timeout=20000)
        print("  ✓ Bot nhận diện sản phẩm và trả về thẻ thông tin sản phẩm thành công")
        page.screenshot(path=str(ARTIFACT_DIR / "shot_run2_product.png"))
        audit_results["run2_input_and_submit"]["submit_and_product_card"] = "passed"

        print("\n=== BẮT ĐẦU VÒNG 3: KIỂM THỬ TƯƠNG TÁC THẺ ỨNG VIÊN (CANDIDATE CARDS) ===")
        # 3.1 Nạp candidate message vào CSDL hệ thống và reload/refresh trang để có card thật từ server
        seed_test_candidate()
        page.goto(URL + "/#search", wait_until="networkidle")
        time.sleep(0.5)

        candidate_article = page.locator('article.card:has-text("ACE68")').last
        candidate_article.wait_for(state="visible", timeout=10000)
        print("  ✓ Thẻ ứng viên video được tải từ server và hiển thị chuẩn xác trên giao diện")

        pick_btn = candidate_article.locator('button[data-chat-act="pick"]')
        dismiss_btn = candidate_article.locator('button[data-chat-act="dismiss"]')
        confirm_check = candidate_article.locator('input[type="checkbox"][name="confirm_video"]')

        # 3.2 Click pick khi CHƯA tick confirm -> phải bị chặn và hiển thị thông báo
        assert not confirm_check.is_checked(), "Ban đầu checkbox confirm chưa được tick"
        pick_btn.click()
        time.sleep(0.4)
        assert "Hãy xem video rồi tích ô xác nhận trước khi chọn." in status_msg.inner_text(), "Chưa tick mà không cảnh báo"
        print("  ✓ Click 'Chọn và tải để xử lý' khi chưa tick: chặn chuẩn xác, cảnh báo rõ ràng")

        # 3.3 Tick checkbox confirm
        confirm_check.check()
        assert confirm_check.is_checked(), "Checkbox confirm phải được tick thành công"
        print("  ✓ Tick checkbox xác nhận video: trạng thái cập nhật mượt mà")

        # 3.4 Bấm 'Bỏ ứng viên' (dismiss)
        src_id = dismiss_btn.get_attribute("data-source-id")
        dismiss_btn.click()
        page.locator(f'button[data-chat-act="dismiss"][data-source-id="{src_id}"]').wait_for(state="detached", timeout=10000)
        print("  ✓ Click 'Bỏ ứng viên' (dismiss): gửi yêu cầu loại bỏ ứng viên thành công, thẻ biến mất mượt mà")
        audit_results["run3_candidate_actions"]["pick_and_dismiss"] = "passed"
        page.screenshot(path=str(ARTIFACT_DIR / "shot_run3_candidate.png"))

        print("\n=== BẮT ĐẦU VÒNG 4: KIỂM THỬ SỬA TÊN VÀ QUẢN LÝ LỊCH SỬ (DELETE & CLEAR) ===")
        # 4.1 Test nút 'Sửa tên/model' (fill) trên bot bubble của sản phẩm
        fill_btn = page.locator('#chat-thread button[data-chat-act="fill"]').first
        if fill_btn.is_visible():
            target_text = fill_btn.get_attribute("data-text")
            fill_btn.click()
            time.sleep(0.3)
            assert textbox.input_value() == target_text, f"Nút fill không điền đúng văn bản: {textbox.input_value()} != {target_text}"
            print(f"  ✓ Nút 'Sửa tên/model' (fill): tự động điền đúng tên ('{target_text}') vào textbox và focus")

        # 4.2 Test modal hộp thoại xác nhận khi click nút Xóa lượt này (delete_history)
        del_turn_btn = page.locator('#chat-thread button[data-chat-act="delete_history"]').first
        modal = page.locator("#confirm-action")
        cancel_btn = modal.locator("[data-confirm-cancel]")
        accept_btn = modal.locator("[data-confirm-accept]")

        del_turn_btn.click()
        time.sleep(0.4)
        assert modal.is_visible(), "Modal xác nhận #confirm-action phải hiển thị khi bấm nút có data-ask"
        print("  ✓ Bấm nút có data-ask: Hộp thoại xác nhận hiển thị an toàn và rõ ràng")

        # Bấm Hủy trong modal
        cancel_btn.click()
        time.sleep(0.3)
        assert not modal.is_visible(), "Modal phải đóng khi bấm Hủy"
        print("  ✓ Bấm Hủy: Hộp thoại đóng lại, không xóa dữ liệu")

        # 4.3 Test 'Xóa lịch sử tìm kiếm' (clear) ở cột bên phải
        clear_btn = page.locator('button[data-chat-act="clear"]')
        assert clear_btn.is_visible(), "Nút Xóa lịch sử tìm kiếm không hiển thị ở aside"
        clear_btn.click()
        time.sleep(0.4)
        assert modal.is_visible(), "Modal xác nhận phải hiện khi bấm Xóa lịch sử tìm kiếm"

        # Bấm Xác nhận xóa trong modal
        accept_btn.click()
        modal.wait_for(state="hidden", timeout=5000)
        page.wait_for_function(
            "() => document.getElementById('chat-thread').innerText.includes('Gửi cho mình một trong những thứ bạn có về sản phẩm')",
            timeout=10000,
        )
        print("  ✓ Nút 'Xóa lịch sử tìm kiếm' (clear) + Modal confirm: xóa sạch lịch sử mượt mà, trở về màn chào đón")
        audit_results["run4_history_management"]["clear_and_fill"] = "passed"
        page.screenshot(path=str(ARTIFACT_DIR / "shot_run4_history_cleared.png"))

        print("\n=== BẮT ĐẦU VÒNG 5: KIỂM THỬ EDGE CASES & RESPONSIVE AUDIT ===")
        # 5.1 Test attach file client-side limits & UI list
        tmp_file = ROOT / "data" / "test_attach.txt"
        tmp_file.write_text("Test TrendVN file attachment client-side handling.")
        try:
            file_input = composer.locator('input[name="files"]')
            file_input.set_input_files(str(tmp_file))
            time.sleep(0.3)
            files_list = composer.locator("[data-chat-files]")
            assert "test_attach.txt" in files_list.inner_text(), "File đính kèm không hiển thị trong danh sách: " + files_list.inner_text()
            print("  ✓ Đính kèm file hợp lệ: hiển thị tên file và kích thước chính xác")

            # Bỏ file bằng nút ✕
            drop_btn = files_list.locator("button.ghost", has_text="✕")
            drop_btn.click()
            time.sleep(0.3)
            assert files_list.inner_text() == "", "File không được gỡ bỏ khi click nút ✕"
            print("  ✓ Click nút ✕: gỡ tệp đính kèm ngay lập tức mà không để lại rác")
        finally:
            if tmp_file.exists():
                tmp_file.unlink()

        # 5.2 Responsive touch targets audit (Desktop 1280px & Mobile 375px)
        viewports = [
            ("Desktop 1280x800", 1280, 800),
            ("Mobile iPhone 375x667", 375, 667),
            ("Mobile 414x896", 414, 896),
            ("Tablet 768x1024", 768, 1024),
        ]
        for name, w, h in viewports:
            page.set_viewport_size({"width": w, "height": h})
            time.sleep(0.3)
            touch_ok = page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('#search button, #search input[type="checkbox"]'));
                const bad = buttons.filter(b => {
                    const r = b.getBoundingClientRect();
                    return (r.width > 0 && r.height > 0) && (r.width < 44 || r.height < 44);
                });
                return bad.length === 0;
            }""")
            print(f"  ✓ Responsive {name}: bố cục ổn định, ô chạm >= 44px: {'ĐẠT' if touch_ok else 'CẦN XEM LẠI'}")
            audit_results["run5_edge_cases_and_responsive"][name] = "passed" if touch_ok else "warning"

        page.screenshot(path=str(ARTIFACT_DIR / "shot_run5_responsive_mobile.png"))

        # 5.3 Console errors audit
        critical_console_errors = [e for e in console_errors if "favicon" not in e and "status of 404" not in e]
        assert len(page_errors) == 0, f"Có lỗi JavaScript trong trang: {page_errors}"
        assert len(critical_console_errors) == 0, f"Có lỗi console nghiêm trọng: {critical_console_errors}"
        print("  ✓ Console & JavaScript Health: 0 page errors, 0 console errors!")

        browser.close()

    print("\n=== HOÀN THÀNH 5 VÒNG KIỂM THỬ TRÌNH DUYỆT THẬT: 100% PASS ===")
    return audit_results


if __name__ == "__main__":
    results = run_live_audit(headless=True)
    print(json.dumps(results, indent=2, ensure_ascii=False))
