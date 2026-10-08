"""Validated discovery choices become actual source queries before the browser searches, never only local filters."""

from .topics import TOPIC_IDS, TOPIC_LABEL

TOPIC_ZH = {
    "music": "音乐 舞蹈",
    "comedy": "搞笑",
    "pets": "萌宠",
    "food": "美食",
    "travel": "旅行",
    "family": "亲子",
    "beauty": "美妆 穿搭",
    "sports": "运动",
    "gaming": "游戏",
    "anime": "动漫",
    "movies": "影视",
    "lifestyle": "生活技巧",
    "knowledge": "科普",
    "news": "热点",
    "entertainment": "娱乐",
}
PRODUCT_CATEGORIES = {
    "electronics": ("Điện tử và phụ kiện", "电子产品 数码配件"),
    "beauty": ("Làm đẹp", "美妆 护肤"),
    "fashion": ("Thời trang", "服装 穿搭"),
    "home": ("Gia dụng", "家居 家用"),
    "baby": ("Mẹ và bé", "母婴"),
    "food": ("Thực phẩm", "食品"),
    "sports": ("Thể thao", "运动用品"),
    "pets": ("Đồ thú cưng", "宠物用品"),
}


def options(payload):
    topic, category, sales = payload.get("topic", ""), payload.get("category", ""), payload.get("sales", False)
    source = payload.get("source", "auto")
    if topic not in ("", *TOPIC_IDS) or category not in ("", *PRODUCT_CATEGORIES) or not isinstance(sales, bool):
        raise ValueError("Thể loại hoặc ngành hàng không hợp lệ")
    if source not in ("auto", "tiktok", "douyin", "kuaishou", "instagram"):
        raise ValueError("Nguồn tìm kiếm không hợp lệ")
    if sales and not category:
        raise ValueError("Chọn ngành hàng để tìm video bán hàng")
    return {"topic": topic, "category": category if sales else "", "sales": sales, "source": source}


def queries(identity, chosen):
    """Keep explicit model identifiers at the beginning when a bounded query needs truncation."""
    base = identity.get("queries", {})
    original = identity.get("query") or identity.get("name", "")
    result = {}
    for source in ("tiktok", "douyin", "kuaishou", "instagram"):
        chinese = source in ("douyin", "kuaishou")
        text = base.get(source) or base.get("douyin" if chinese else "tiktok") or original
        topic = (TOPIC_ZH if chinese else TOPIC_LABEL).get(chosen.get("topic"), "")
        category = PRODUCT_CATEGORIES.get(chosen.get("category"))
        category = category[1 if chinese else 0] if category else ""
        intent = ("好物 推荐" if chinese else "review sản phẩm") if chosen.get("sales") else ""
        result[source] = " ".join(dict.fromkeys(part.strip() for part in (text, topic, category, intent) if part.strip()))[:160]
    return result


def fallback_text(chosen):
    """A genre/category alone is sufficient input for discovery."""
    if chosen["sales"]:
        return PRODUCT_CATEGORIES[chosen["category"]][0]
    return TOPIC_LABEL.get(chosen["topic"], "")
