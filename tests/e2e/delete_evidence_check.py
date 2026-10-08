"""Exercise deletion proof observers on disposable HTML, never TikTok or the live account."""

import runpy
import time
import uuid
from pathlib import Path


def check_deletion_notices(browser, check):
    module = runpy.run_path(str(Path(__file__).resolve().parents[2] / "services/agent/src/trendvn_agent/publisher/delete_evidence.py"))
    page = browser.new_page()
    try:
        page.set_content('<main><div role="status" id="notices"></div></main>')
        module["arm_notice"](page)
        page.evaluate("""() => {
          const toast=document.createElement('div');
          toast.innerHTML='<span>Đã xóa video.</span><button>Đóng</button>';
          document.querySelector('#notices').appendChild(toast);
          setTimeout(()=>toast.remove(),5);
        }""")
        page.wait_for_function("() => !document.querySelector('#notices').textContent")
        check("Delete: short toast with close control survives removal", page.evaluate(module["READY"]))
        module["wait_notice"](page)
        check("Delete: observer cleans up after success", page.evaluate("() => !window.__trendvnDeleteProof"))
        module["arm_notice"](page)
        page.evaluate("""() => {
          document.querySelector('#notices').innerHTML='<span>Không tìm thấy kết quả</span><span hidden>Đã xóa video.</span><span style="visibility:hidden">Đã xóa video.</span><div style="visibility:hidden"><span>Video deleted.</span></div><div style="opacity:0"><span>Post deleted.</span></div>';
          const text=document.createElement('p');text.textContent='Đã xóa video.';document.body.appendChild(text);
        }""")
        check("Delete: empty results, hidden and unrelated text cannot prove success", not page.evaluate(module["READY"]))
        page.evaluate(module["STOP"])
        page.set_content('<div role="status" id="notices"></div>')
        module["arm_notice"](page)
        page.evaluate("() => document.querySelector('#notices').innerHTML='<span style=\"visibility:hidden\">Đã xóa video.</span>'")
        check("Delete: visible container cannot turn its hidden child into proof", not page.evaluate(module["READY"]))
        page.evaluate(module["STOP"])
    finally:
        page.close()


def check_owner_resolution(page, base, store, calls, go, check):
    """The owner's result updates only the isolated worker and cannot send another deletion."""
    jid, now = uuid.uuid4().hex, time.time()
    username = store.account("main")["username"]
    url = "https://www.tiktok.com/@%s/video/7690000000000000099" % username
    with store.transaction() as db:
        db.execute(
            "INSERT INTO jobs(id,platform,source_id,url,title,state,first_seen,last_seen,updated,account,target,publish_url,published_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (jid, "manual", jid, url, "Bài kiểm kết quả xóa", "published", now, now, now, "main", username, url, now),
        )
    grant = store.delete_post_begin(jid, url, "main")["grant"]
    store.delete_post_claim(jid, grant)
    store.delete_post_finish(jid, grant, "unknown")
    before, requests = store.published_today(), len(calls)
    go(page, base + "/#posted")
    row = page.get_by_role("row").filter(has_text="Bài kiểm kết quả xóa")
    check("Delete: unknown result offers both owner checks", row.get_by_role("button", name="Đã kiểm tra: bài vẫn còn").is_visible())
    row.get_by_role("button", name="Đã kiểm tra: bài đã xóa").click()
    page.locator("#confirm-action [data-confirm-accept]").click()
    page.wait_for_function("() => document.querySelector('#posted').textContent.includes('Chủ đã kiểm tra: bài đã xóa')")
    check("Delete: owner confirmation records its distinct evidence", "Chủ đã kiểm tra: bài đã xóa" in row.inner_text())
    check(
        "Delete: reconcile sends no browser action and keeps posting history", len(calls) == requests and store.published_today() == before
    )
    check("Delete: reconciled post has no second delete button", row.get_by_role("button").count() == 0)
