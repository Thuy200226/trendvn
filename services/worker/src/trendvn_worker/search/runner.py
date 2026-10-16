"""The work behind a chat answer: recognise a product, find videos in the owner's account, check a pasted link, download a pick.
Each function finishes its chat message ('done' or 'error') and returns one line for the task's step log; the caller only runs it."""

import json
import time
import uuid

from . import affiliate
from ..domain import discovery
from ..domain.product_binding import catalog_binding, strict_title
from ..domain.platforms import COUNTRIES
from ..domain.product_links import classify
from .identify import from_page, identify, video_identity

SEARCH_TIMEOUT = None  # each source bounds result loading; a visible verification window waits for its owner
HUMAN_TIMEOUT = None  # wait until the owner completes verification or closes the window
SIGN_IN_TIMEOUT = None  # a human login has no arbitrary deadline
CHECK_TIMEOUT = None  # bounded page read except an owner verification wall, which waits without a deadline


def recognise_product(store, mid, reference, agent=None):
    message = store.chat_get(mid)
    expected = message["body"].get("account_username")
    identity = identify(store, reference)
    chosen = message["body"].get("discovery")
    if chosen:
        identity["queries"] = discovery.queries(identity, chosen)
        if chosen.get("sales"):
            identity["matched_affiliate"] = catalog_binding(
                identity, store.commission_list(message["account"]), message["account"], expected
            )
    store.chat_set(mid, "done", identity=identity)
    if chosen and agent:
        account = store.account(message["account"])
        if not account or not expected or account["username"] != expected:
            raise ValueError("Tài khoản đã thay đổi từ lúc gửi; hãy tìm lại")
        body = {
            "identity": identity,
            "source": chosen["source"],
            "product": mid,
            "turn_id": mid,
            "discovery": chosen,
            "account_username": expected,
            "results": [],
            "note": "",
        }
        answer = store.chat_add("bot", "videos", body, state="running", account=message["account"])
        try:
            find_videos(store, answer, agent)
        except Exception as error:
            store.chat_set(answer, "error", error=str(error)[:700])
            return "Đã nhận diện; tìm video chưa thành công: " + str(error)[:300]
    return "Đã nhận diện: " + (identity.get("name") or identity["query"])


def check_link(store, mid):
    """Resolve the pasted link, judge it against the product in the chat, and keep it when nothing is left to doubt."""
    message = store.chat_get(mid)
    found = affiliate.inspect(message["body"]["url"])
    if found["kind"] == "video":  # a short link shared from a video: not a product, but exactly what the owner may want to look up
        video = classify(found["final"])["canonical"]
        product = store.chat_add(
            "bot", "product", {"identity": video_identity([video]), "from_video": True, "turn_id": mid}, account=message["account"]
        )
        store.chat_set(mid, "done", video=video, product=product)
        return "Link này là một video, không phải trang sản phẩm"
    product = store.chat_product(message["account"])
    identity = product["body"]["identity"] if product else {}
    result = affiliate.verdict(identity, found, store.commission_known(message["account"]))
    fields = {"found": found, "verdict": result, "product": product["id"] if product else None}
    if not identity and found["product_id"] and found["title"]:
        fields["product"] = store.chat_add(
            "bot",
            "product",
            {"identity": from_page(found["title"], found["product_id"]), "from_link": True, "turn_id": mid},
            account=message["account"],
        )
    if result["verdict"] in ("exact", "found") and not result["needs_confirmation"]:
        store.commission_save(message["account"], found)
        fields["saved"] = True
    store.chat_set(mid, "done", **fields)
    return result["summary"]


def find_videos(store, mid, agent, human=False):
    """Ask the agent to look in the chosen account's own browser session; the candidates are ranked against the product."""
    message = store.chat_get(mid)
    body = message["body"]
    identity = body["identity"]
    discovery_opt = body.get("discovery") or {}
    response = agent(
        "/api/search/open" if human else "/api/search",
        {
            "account": message["account"], "query": identity["query"], "queries": identity.get("queries", {}),
            "source": body["source"], "links": identity.get("links", []), "require_session": True, "restore_sessions": True,
            "discovery": discovery_opt, "sales": bool(discovery_opt.get("sales")),
            "sources": [p for p, state in store.channel_states().get(message["account"], {}).items() if state["state"] in ("ok", "wall")],
        },
        HUMAN_TIMEOUT if human else SEARCH_TIMEOUT,
    )  # fmt: skip
    ranked = store.videos_rank(mid, response.get("items", []), limit=40)
    results, existing = store.videos_new(ranked)
    results = results[:20]
    note = response.get("note", "")
    if existing:
        note += " · Bỏ qua %d video đã có trong hệ thống; không tải lại." % existing
    if (body.get("discovery") or {}).get("sales"):
        note += (
            " · Xếp theo độ khớp, lượt xem và lượt thích đã đọc được. Nguồn chưa cung cấp số bán nên chưa xác nhận sản phẩm bán chạy nhất."
        )
    store.chat_set(mid, "done", results=store.chat_find_results(mid, results), existing=existing, note=note)
    return "Tìm thấy %d ứng viên. Hãy xem và chọn trong khung chat." % len(results)


def sign_in(store, mid, agent, check=False):
    """Open the owner's window to sign in to a channel (or only look whether the profile is signed in), and say how it went in the chat."""
    message = store.chat_get(mid)
    channel = message["body"]["channel"]
    if (store.account(message["account"]) or {}).get("username") != message["body"].get("account_username"):
        raise ValueError("Tài khoản đã thay đổi; hãy mở lại đăng nhập")
    payload = {"account": message["account"], "channel": channel}

    def remember(ok, who="", state=None):
        if (store.account(message["account"]) or {}).get("username") != message["body"].get("account_username"):
            raise ValueError("Tài khoản đã thay đổi trong lúc đăng nhập; hãy kiểm tra lại đúng tài khoản")
        if channel == "tiktok" and who and who.casefold() != message["body"]["account_username"].casefold():
            raise ValueError("Phiên TikTok không thuộc tài khoản đã chọn; hãy đăng nhập đúng tài khoản")
        store.channel_report(message["account"], channel, state or ("ok" if ok else "out"), who, message["body"]["account_username"])

    if check:
        result = agent("/api/channel/check", payload, CHECK_TIMEOUT)
        ok = bool(result.get("logged_in"))
        state = result.get("state", "ok" if ok else "out")
        remember(ok, result.get("who", ""), state)
        store.chat_set(mid, "done", ok=ok, who=result.get("who", ""), session_state=state)
        return {
            "ok": "Đã kiểm chứng phiên đăng nhập",
            "out": "Chưa đăng nhập",
            "wall": "Chờ bạn xác minh Douyin",
            "unknown": "Chưa kiểm chứng được phiên; giữ hồ sơ đã lưu",
        }[state]
    result = agent("/api/channel/login", payload, SIGN_IN_TIMEOUT)
    remember(bool(result.get("ok")), result.get("who", ""), result.get("state"))
    if not result.get("ok"):
        raise ValueError(result.get("reason") or "Chưa đăng nhập được")
    store.chat_set(mid, "done", ok=True, who=result.get("who", ""))
    return "Đã đăng nhập"


def download_video(store, jid, agent):
    selected = store.videos_media_ready(jid)
    result = agent("/api/search/download", {"account": selected["account"], "job_id": jid, "item": selected["item"]}, SEARCH_TIMEOUT)
    return "Video đã tải và vào hàng đợi xử lý." if result.get("state") == "queued" else "Video trùng dữ liệu đã có; không xử lý trùng."


def _batch_product(store, product, account, username):
    if not isinstance(product, dict) or any(not isinstance(product.get(k, ""), str) for k in ("name", "brand", "model", "variant")):
        raise ValueError("Thông tin sản phẩm chưa hợp lệ")
    identity = {k: product.get(k, "") for k in ("name", "brand", "model", "variant", "product_id")}
    query = product.get("query_zh") or (identity["brand"] + " " + identity["model"]).strip()
    if product.get("is_showcase") or identity["brand"] == "Showcase":
        observed = identify(store, {"text": identity["name"], "files": [], "sales": True})
        identity.update({k: observed.get(k, "") for k in ("brand", "model", "variant")})
        query = (observed.get("queries") or {}).get("douyin") or query
    binding = catalog_binding(identity, store.commission_list(account), account, username)
    if not binding:
        raise ValueError("Chưa có mã Shop duy nhất đúng hãng/model/biến thể; chưa tìm hoặc gắn giỏ")
    if not isinstance(query, str) or not 1 <= len(query) <= 160:
        raise ValueError("Chưa có từ khóa tìm sản phẩm hợp lệ")
    return identity, binding, query


def _batch_video(store, mid, identity, response):
    ranked = [
        i
        for i in store.videos_rank(mid, response.get("items") or [], limit=20, identity=identity)
        if strict_title(identity, i.get("title", ""))
    ]
    results, _ = store.videos_new(ranked)
    return next(
        (
            i
            for i in results
            if isinstance(i.get("duration"), (int, float)) and not isinstance(i["duration"], bool) and 10 <= i["duration"] <= 180
        ),
        None,
    )


def _batch_insert(store, mid, video, identity, binding, account, username):
    from ..domain.product_binding import validate_binding

    jid, now = uuid.uuid4().hex, time.time()
    with store.transaction() as db:
        receiver = db.execute("SELECT username,enabled FROM accounts WHERE id=?", (account,)).fetchone()
        if not receiver or not receiver[1] or receiver[0] != username:
            raise ValueError("Tài khoản đã thay đổi; dừng tạo giỏ hàng")
        links = [dict(r) for r in db.execute("SELECT account,url,title,product_id FROM commission_links WHERE account=?", (account,))]
        validate_binding(binding, links, account, username)
        platform = video.get("platform") or "douyin"
        if db.execute(
            "SELECT 1 FROM jobs WHERE url=? OR (platform=? AND source_id=?)", (video["url"], platform, video["source_id"])
        ).fetchone():
            raise ValueError("Video đã có trong hệ thống; không lấy lại")
        metadata = {"product_reference": identity, "search_username": username, "product_binding": binding, "commerce_required": True}
        db.execute(
            "INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,last_seen,state,reason,updated,meta,search_id,search_account,target,product_binding) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                jid,
                platform,
                video["source_id"],
                video["url"],
                COUNTRIES[platform],
                video["title"],
                now,
                now,
                "candidate",
                "Đã chọn đúng model; cần kiểm nội dung sau dựng",
                now,
                json.dumps(metadata),
                str(mid),
                account,
                username,
                json.dumps(binding),
            ),
        )
    return jid


def _batch_one(store, mid, product, account, username, agent):
    identity, binding, query = _batch_product(store, product, account, username)
    if (store.account(account) or {}).get("username") != username:
        raise ValueError("Tài khoản đã thay đổi; dừng tìm")
    response = agent(
        "/api/search",
        {
            "account": account,
            "query": query,
            "queries": {"douyin": query},
            "source": "douyin",
            "sales": True,
            "require_session": True,
            "sources": ["douyin"],
        },
        SEARCH_TIMEOUT,
    )
    video = _batch_video(store, mid, identity, response)
    if not video:
        raise ValueError("Chưa có video mới đúng hãng/model/biến thể; không lấy video khác thay thế")
    jid = _batch_insert(store, mid, video, identity, binding, account, username)
    result = agent("/api/search/download", {"job_id": jid, "account": account, "item": video}, SEARCH_TIMEOUT)
    state = result.get("state") or result.get("status")
    if state != "queued":
        raise ValueError("Video chưa vào hàng chờ (%s); không coi là đã xử lý thành công" % state)
    return {"job_id": jid, "product_name": identity["name"], "video_title": video["title"], "likes": video.get("likes"), "state": state}


def batch_sales_search(store, mid, agent):
    """Each product gets its own exact catalog/video decision; ambiguity never creates a cart."""
    message = store.chat_get(mid)
    body, account = message["body"], message["account"]
    username = (store.account(account) or {}).get("username")
    if not username or body.get("account_username") != username:
        raise ValueError("Tài khoản đã thay đổi; hãy gửi lại lượt hàng loạt")
    products = body.get("products") or []
    created, logs = [], []
    for index, product in enumerate(products):
        store.chat_set(mid, "running", current=index + 1, logs=logs[-10:], created_jobs=created)
        try:
            result = _batch_one(store, mid, product, account, username, agent)
            created.append(result)
            logs.append("✓ Đã tải đúng video cho " + result["product_name"])
        except Exception as error:
            logs.append("⚠️ Sản phẩm %d: %s" % (index + 1, str(error)[:180]))
    summary = "Đã tải %d/%d sản phẩm vào chờ xử lý và kiểm nội dung trước khi gắn giỏ/đăng." % (len(created), len(products))
    store.chat_set(mid, "done", current=len(products), created_jobs=created, logs=logs, summary=summary)
    return summary


def run(store, kind, key, agent, reference=None):
    """Do one chat job. Returns (ok, line for the step log); the message is never left unfinished."""
    try:
        if kind == "search_download":
            return True, download_video(store, key, agent)
        mid = int(key)
        if kind == "identify":
            return True, recognise_product(store, mid, reference, agent)
        if kind == "link":
            return True, check_link(store, mid)
        if kind in ("channel_login", "channel_check"):
            return True, sign_in(store, mid, agent, check=kind == "channel_check")
        if kind == "batch_sales_search":
            return True, batch_sales_search(store, mid, agent)
        return True, find_videos(store, mid, agent, human=kind == "search_human")
    except Exception as error:
        text = str(error)[:700]
        if kind == "search_download":
            store.video_download_failed(key, text)
        else:
            store.chat_set(int(key), "error", error=text)
        return False, text
