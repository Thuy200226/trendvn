"""The work behind a chat answer: recognise a product, find videos in the owner's account, check a pasted link, download a pick.
Each function finishes its chat message ('done' or 'error') and returns one line for the task's step log; the caller only runs it."""

from . import affiliate
from ..domain.product_links import classify
from .identify import from_page, identify, video_identity

SEARCH_TIMEOUT = 180
HUMAN_TIMEOUT = 360  # a window where the owner solves the site's own check by hand
SIGN_IN_TIMEOUT = 11 * 60  # the agent waits up to ten minutes for the owner to sign in
CHECK_TIMEOUT = 90  # reading a profile's cookies


def recognise_product(store, mid, reference):
    identity = identify(store, reference)
    store.chat_set(mid, "done", identity=identity)
    return "Đã nhận diện: " + (identity.get("name") or identity["query"])


def check_link(store, mid):
    """Resolve the pasted link, judge it against the product in the chat, and keep it when nothing is left to doubt."""
    message = store.chat_get(mid)
    found = affiliate.inspect(message["body"]["url"])
    if found["kind"] == "video":  # a short link shared from a video: not a product, but exactly what the owner may want to look up
        video = classify(found["final"])["canonical"]
        product = store.chat_add("bot", "product", {"identity": video_identity([video]), "from_video": True}, account=message["account"])
        store.chat_set(mid, "done", video=video, product=product)
        return "Link này là một video, không phải trang sản phẩm"
    product = store.chat_product()
    identity = product["body"]["identity"] if product else {}
    result = affiliate.verdict(identity, found, store.commission_known(message["account"]))
    fields = {"found": found, "verdict": result, "product": product["id"] if product else None}
    if not identity and found["product_id"] and found["title"]:
        fields["product"] = store.chat_add(
            "bot", "product", {"identity": from_page(found["title"], found["product_id"]), "from_link": True}, account=message["account"]
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
    response = agent(
        "/api/search/open" if human else "/api/search",
        {
            "account": message["account"], "query": identity["query"], "queries": identity.get("queries", {}),
            "source": body["source"], "links": identity.get("links", []),
        },
        HUMAN_TIMEOUT if human else SEARCH_TIMEOUT,
    )  # fmt: skip
    results = store.videos_rank(mid, response.get("items", []))
    store.chat_set(mid, "done", results=results, note=response.get("note", ""))
    return "Tìm thấy %d ứng viên. Hãy xem và chọn trong khung chat." % len(results)


def sign_in(store, mid, agent, check=False):
    """Open the owner's window to sign in to a channel (or only look whether the profile is signed in), and say how it went in the chat."""
    message = store.chat_get(mid)
    channel = message["body"]["channel"]
    payload = {"account": message["account"], "channel": channel}
    if check:
        result = agent("/api/channel/check", payload, CHECK_TIMEOUT)
        ok = bool(result.get("logged_in"))
        store.chat_set(mid, "done", ok=ok, who="")
        return "Đã đăng nhập" if ok else "Chưa đăng nhập"
    result = agent("/api/channel/login", payload, SIGN_IN_TIMEOUT)
    if not result.get("ok"):
        raise ValueError(result.get("reason") or "Chưa đăng nhập được")
    store.chat_set(mid, "done", ok=True, who=result.get("who", ""))
    return "Đã đăng nhập"


def download_video(store, jid, agent):
    selected = store.videos_media_ready(jid)
    result = agent("/api/search/download", {"account": selected["account"], "job_id": jid, "item": selected["item"]}, SEARCH_TIMEOUT)
    return "Video đã tải và vào hàng đợi xử lý." if result.get("state") == "queued" else "Video trùng dữ liệu đã có; không xử lý trùng."


def run(store, kind, key, agent, reference=None):
    """Do one chat job. Returns (ok, line for the step log); the message is never left unfinished."""
    try:
        if kind == "search_download":
            return True, download_video(store, key, agent)
        mid = int(key)
        if kind == "identify":
            return True, recognise_product(store, mid, reference)
        if kind == "link":
            return True, check_link(store, mid)
        if kind in ("channel_login", "channel_check"):
            return True, sign_in(store, mid, agent, check=kind == "channel_check")
        return True, find_videos(store, mid, agent, human=kind == "search_human")
    except Exception as error:
        text = str(error)[:700]
        if kind == "search_download":
            store.video_download_failed(key, text)
        else:
            store.chat_set(int(key), "error", error=text)
        return False, text
