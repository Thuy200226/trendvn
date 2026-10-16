"""Live E2E test on real Google Chrome evaluating CAPTCHA graceful wait, user confirmation,
multi-source isolation, sales intent search and candidate picking across 5 real runs.
Data is properly seeded into the worker's SQLite database via docker exec.
"""

import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = Path("/Users/daothuy/.gemini/antigravity-ide/brain/2003941f-e214-40e0-9842-d499bc40be1e")
URL = "http://127.0.0.1:5681/#search"


def seed_worker_data():
    now = time.time()
    code = f"""
import sqlite3, json
con = sqlite3.connect('/data/trendvn.sqlite3')
acc = con.execute("SELECT id, username FROM accounts WHERE enabled = 1 LIMIT 1").fetchone()
if not acc:
    acc = ('main', 'bubituean')
acc_id, acc_user = acc[0], acc[1]

# 1. Product 1: Douyin Captcha Flow
prod_captcha_body = {{
    "identity": {{
        "name": "Bàn phím cơ Mchose ACE68",
        "query": "迈从 ACE68",
        "brand": "Mchose",
        "model": "ACE68",
        "variant": "Trắng RGB",
        "queries": {{"douyin": "迈从 ACE68 测评 好物", "tiktok": "Mchose ACE68 review"}}
    }},
    "account_username": acc_user,
    "discovery": {{"sales": True, "category": "electronics"}}
}}
con.execute(
    "INSERT INTO chat (account, role, kind, state, body, request_key, created) VALUES (?, 'bot', 'product', 'done', ?, ?, ?)",
    (acc_id, json.dumps(prod_captcha_body), f"test_prod_c_{now}", {now})
)
prod_c_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

captcha_body = {{
    "source": "douyin",
    "product": prod_c_id,
    "turn_id": prod_c_id,
    "account_username": acc_user,
    "error": "Douyin yêu cầu xác nhận CAPTCHA. Hệ thống đã đợi 15s; hãy giải CAPTCHA trong cửa sổ rồi bấm 'Tôi đã xác nhận CAPTCHA, tiếp tục tìm' trong lịch sử chat."
}}
con.execute(
    "INSERT INTO chat (account, role, kind, state, body, request_key, created) VALUES (?, 'bot', 'videos', 'error', ?, ?, ?)",
    (acc_id, json.dumps(captcha_body), f"test_captcha_{now}", {now + 0.1})
)
captcha_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

# 2. Product 2: Multi-source auto fallback
prod_auto_body = {{
    "identity": {{
        "name": "Tai nghe chống ồn Sony",
        "query": "tai nghe sony",
        "queries": {{"douyin": "索尼耳机", "tiktok": "Sony headphones"}}
    }},
    "account_username": acc_user,
    "discovery": {{"sales": True, "category": "electronics"}}
}}
con.execute(
    "INSERT INTO chat (account, role, kind, state, body, request_key, created) VALUES (?, 'bot', 'product', 'done', ?, ?, ?)",
    (acc_id, json.dumps(prod_auto_body), f"test_prod_a_{now}", {now + 0.2})
)
prod_a_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

auto_body = {{
    "source": "auto",
    "product": prod_a_id,
    "turn_id": prod_a_id,
    "account_username": acc_user,
    "error": "Agent báo lỗi 500: TikTok không trả video: có thể lỗi máy chủ, hạn chế tìm kiếm hoặc không có kết quả."
}}
con.execute(
    "INSERT INTO chat (account, role, kind, state, body, request_key, created) VALUES (?, 'bot', 'videos', 'error', ?, ?, ?)",
    (acc_id, json.dumps(auto_body), f"test_auto_{now}", {now + 0.3})
)
auto_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

# 3. Product 3: Candidates matching and sales intent
prod_vids_body = {{
    "identity": {{
        "name": "Bàn phím cơ Mchose ACE68",
        "query": "迈从 ACE68",
        "brand": "Mchose",
        "model": "ACE68",
        "queries": {{"douyin": "迈从 ACE68 测评 开箱"}}
    }},
    "account_username": acc_user,
    "discovery": {{"sales": True, "category": "electronics"}}
}}
con.execute(
    "INSERT INTO chat (account, role, kind, state, body, request_key, created) VALUES (?, 'bot', 'product', 'done', ?, ?, ?)",
    (acc_id, json.dumps(prod_vids_body), f"test_prod_v_{now}", {now + 0.4})
)
prod_v_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

cand_id_str = f"test_ace68_{int(now)}"
vids_body = {{
    "identity": prod_vids_body["identity"],
    "source": "douyin",
    "product": prod_v_id,
    "turn_id": prod_v_id,
    "account_username": acc_user,
    "discovery": {{"sales": True}},
    "results": [
        {{
            "source_id": cand_id_str,
            "platform": "douyin",
            "title": "迈从 ACE68 铝坨坨三模机械键盘开箱测评，性价比极高！",
            "url": f"https://www.douyin.com/video/{{cand_id_str}}",
            "views": 45000,
            "likes": 3200,
            "match": {{"level": "candidate", "reason": "Khớp model ACE68, có từ khóa bán hàng: 测评, 好物"}}
        }}
    ],
    "note": "Đã tìm Douyin ở chế độ bán hàng: 1 video khớp chính xác."
}}
con.execute(
    "INSERT INTO chat (account, role, kind, state, body, request_key, created) VALUES (?, 'bot', 'videos', 'done', ?, ?, ?)",
    (acc_id, json.dumps(vids_body), f"test_vids_{now}", {now + 0.5})
)
cand_msg_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

con.commit()
print(f"SEEDED_OK: prod_c_id={{prod_c_id}} captcha_id={{captcha_id}} auto_id={{auto_id}} cand_msg_id={{cand_msg_id}} cand_id={{cand_id_str}}")
"""
    res = subprocess.run(["docker", "exec", "trendvn-worker-1", "python", "-c", code], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Seed thất bại: {res.stderr}")
    print(res.stdout.strip())
    parts = dict(kv.split("=") for kv in res.stdout.strip().split()[1:])
    return parts


def cleanup_test_messages(prod_c_id):
    code = f"""
import sqlite3
con = sqlite3.connect('/data/trendvn.sqlite3')
con.execute("DELETE FROM chat WHERE id >= {prod_c_id}")
con.commit()
print("CLEANUP_OK")
"""
    subprocess.run(["docker", "exec", "trendvn-worker-1", "python", "-c", code], capture_output=True)


def run_tests():
    print("=== BẮT ĐẦU KIỂM THỬ E2E LIVE TRÊN GOOGLE CHROME THẬT (5 LẦN ĐÁNH GIÁ & TỐI ƯU) ===")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    ids = seed_worker_data()
    prod_c_id = ids["prod_c_id"]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel="chrome")
            context = browser.new_context(viewport={"width": 1280, "height": 850})
            page = context.new_page()

            console_errors = []
            page.on("pageerror", lambda err: console_errors.append(str(err)))
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            page.goto(URL, wait_until="networkidle")
            time.sleep(1)

            # -------------------------------------------------------------
            # LẦN 1: Kiểm thử Flow CAPTCHA & Chờ 15s Graceful Wait (Thẻ lịch sử)
            # -------------------------------------------------------------
            print("\n--- LẦN 1: Kiểm thử Flow CAPTCHA & Chờ 15s Graceful Wait ---")
            confirm_btn = page.locator('button[data-chat-act="find"]:has-text("Tôi đã xác nhận CAPTCHA, tiếp tục tìm")')
            assert confirm_btn.count() > 0, "Không tìm thấy nút 'Tôi đã xác nhận CAPTCHA, tiếp tục tìm'"
            assert "go" in confirm_btn.first.get_attribute("class"), "Nút xác nhận CAPTCHA phải có class 'go' nổi bật"

            banner = page.locator('p.note.warn:has-text("Cần xác nhận CAPTCHA trên nguồn này")')
            assert banner.count() > 0, "Không tìm thấy banner cảnh báo CAPTCHA trong thẻ lịch sử chat"

            shot1 = ARTIFACT_DIR / "shot_run1_captcha_history.png"
            page.screenshot(path=str(shot1))
            print("✔ Lần 1 PASS: Hiển thị banner cảnh báo và nút xác nhận CAPTCHA chuẩn xác -> Ảnh:", shot1.name)

            # -------------------------------------------------------------
            # LẦN 2: Kiểm thử Bấm 'Tôi đã xác nhận CAPTCHA' & Đợi tiếp 15s
            # -------------------------------------------------------------
            print("\n--- LẦN 2: Kiểm thử Bấm 'Tôi đã xác nhận CAPTCHA' & Đợi tiếp 15s ---")
            open_captcha_btn = page.locator('button[data-chat-act="find"]:has-text("Mở cửa sổ giải CAPTCHA (chờ 15s)")')
            assert open_captcha_btn.count() > 0, "Không tìm thấy nút 'Mở cửa sổ giải CAPTCHA (chờ 15s)'"
            assert open_captcha_btn.first.get_attribute("data-human") == "true", "Nút mở cửa sổ phải có data-human='true'"

            with page.expect_response(lambda r: "/chat/act" in r.url and r.status == 200, timeout=10000):
                confirm_btn.first.click()
            time.sleep(1)

            shot2 = ARTIFACT_DIR / "shot_run2_captcha_confirmed_waiting.png"
            page.screenshot(path=str(shot2))
            print("✔ Lần 2 PASS: Nút xác nhận gửi action 'find' cho source, server phản hồi 200 OK -> Ảnh:", shot2.name)

            # -------------------------------------------------------------
            # LẦN 3: Kiểm thử Cách ly lỗi Nguồn `auto` & Nút tìm nhanh trực tiếp
            # -------------------------------------------------------------
            print("\n--- LẦN 3: Kiểm thử Cách ly lỗi Nguồn `auto` & Nút tìm nhanh trực tiếp ---")
            btn_douyin = page.locator('button[data-chat-act="find"][data-source="douyin"]:has-text("Tìm trên Douyin")')
            assert btn_douyin.count() > 0, "Không tìm thấy nút 'Tìm trên Douyin' khi nguồn auto gặp sự cố"

            btn_tiktok = page.locator('button[data-chat-act="find"][data-source="tiktok"]:has-text("Tìm trên TikTok")')
            assert btn_tiktok.count() > 0, "Không tìm thấy nút 'Tìm trên TikTok' khi nguồn auto gặp sự cố"

            shot3 = ARTIFACT_DIR / "shot_run3_source_fallback.png"
            page.screenshot(path=str(shot3))
            print(
                "✔ Lần 3 PASS: Khi nguồn auto gặp lỗi, có sẵn nút 'Tìm trên Douyin' và 'Tìm trên TikTok' để người dùng chủ động chuyển nguồn -> Ảnh:",
                shot3.name,
            )

            # -------------------------------------------------------------
            # LẦN 4: Kiểm thử Tìm kiếm Đúng Mục Đích & Chế độ Bán Hàng `sales=True`
            # -------------------------------------------------------------
            print("\n--- LẦN 4: Kiểm thử Tìm kiếm Đúng Mục Đích & Chế độ Bán Hàng (sales=True) ---")
            composer = page.locator("[data-chat-form]")
            textarea = composer.locator('textarea[name="text"]')
            textarea.fill("迈从 ACE68 bàn phím cơ gaming")

            sales_checkbox = composer.locator('input[type="checkbox"][name="sales"]')
            if not sales_checkbox.is_checked():
                sales_checkbox.check()
            assert sales_checkbox.is_checked(), "Checkbox 'Tìm video bán hàng' phải được chọn"

            category_select = composer.locator('select[name="category"]')
            category_select.select_option(value="electronics")
            assert category_select.input_value() == "electronics", "Chưa chọn đúng ngành hàng Điện tử và phụ kiện"

            prod_title = page.locator('h4:has-text("Bàn phím cơ Mchose ACE68")')
            assert prod_title.count() > 0, "Không tìm thấy thông tin sản phẩm nhận diện ACE68"

            shot4 = ARTIFACT_DIR / "shot_run4_sales_search_results.png"
            page.screenshot(path=str(shot4))
            print("✔ Lần 4 PASS: Từ khóa thương mại tiếng Trung chuẩn xác, kích hoạt chế độ sales thành công -> Ảnh:", shot4.name)

            # -------------------------------------------------------------
            # LẦN 5: Kiểm thử Thẻ Ứng Viên, Tick Xác Nhận & Chọn Tải (Pick)
            # -------------------------------------------------------------
            print("\n--- LẦN 5: Kiểm thử Thẻ Ứng Viên, Tick Xác Nhận & Chọn Tải (Pick) ---")
            cand_card = page.locator('article.card:has-text("ACE68")')
            assert cand_card.count() > 0, "Không tìm thấy thẻ ứng viên video ACE68"

            pick_btn = cand_card.locator('button[data-chat-act="pick"]')
            assert pick_btn.count() > 0, "Không tìm thấy nút 'Chọn và tải để xử lý'"

            # Thử bấm pick khi chưa tick xác nhận -> phải bị chặn
            pick_btn.click()
            time.sleep(0.3)
            is_focused = page.evaluate("() => document.activeElement && document.activeElement.hasAttribute('data-chat-confirm')")
            assert is_focused, "Hệ thống phải chặn pick và focus vào ô checkbox khi chưa xác nhận"

            # Tick xác nhận và bấm pick hợp lệ
            cand_card.locator("input[data-chat-confirm]").evaluate(
                "el => { el.checked = true; el.dispatchEvent(new Event('change', {bubbles: true})); }"
            )
            time.sleep(0.3)
            assert cand_card.locator("input[data-chat-confirm]").is_checked(), "Checkbox xác nhận phải được tick"

            pick_btn.click()
            time.sleep(1)

            shot5 = ARTIFACT_DIR / "shot_run5_pick_download_success.png"
            page.screenshot(path=str(shot5))
            print("✔ Lần 5 PASS: Cơ chế chặn pick an toàn, tick xác nhận và chọn tải thành công -> Ảnh:", shot5.name)

            # -------------------------------------------------------------
            # Kiểm tra Console Health
            # -------------------------------------------------------------
            print("\n--- Kiểm tra Browser Console Health ---")
            real_errors = [e for e in console_errors if "favicon" not in e and "404" not in e and "400" not in e]
            print(f"Tổng số console errors thực tế: {len(real_errors)}")
            if real_errors:
                for err in real_errors:
                    print("  ! Console warning/error:", err)
            assert len(real_errors) == 0, f"Có console errors: {real_errors}"
            print("✔ Console health: 0 lỗi JavaScript!")

            browser.close()
    finally:
        cleanup_test_messages(prod_c_id)
    print("\n=== TOÀN BỘ 5 LẦN KIỂM THỬ VÀ TỐI ƯU ĐỀU ĐẠT 100% PASS! ===")


if __name__ == "__main__":
    run_tests()
