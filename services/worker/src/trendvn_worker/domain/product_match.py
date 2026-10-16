"""Does a title, or a product id, belong to the product the owner asked for? Labels are evidence, never a probability: a model that does
not match excludes a candidate even when most keywords overlap, and keyword overlap alone is only ever a 'candidate' for a person to check.
"""

import re
import unicodedata

from .search_queries import KNOWN_BRANDS, SPEC_UNITS, normalized

# Words that make another product of the same model number ("Galaxy S24" and "Galaxy S24 Ultra"): a title carrying one the owner did not
# ask for is a different product.
VARIANT_WORDS = {"ultra", "pro", "max", "plus", "mini", "lite", "fe", "air", "turbo", "gt", "v2"}
# A number with its unit is a specification (256GB, 5000mAh), not part of the model's name.
SPEC = re.compile(r"(\d+)\s*(?:%s)(?![a-z0-9])" % SPEC_UNITS)
FACETS = (("brand", "Thương hiệu"), ("model", "Model"), ("variant", "Biến thể"))

NEGATIVE_OLD_WORDS_ZH = (
    "二手",
    "翻新",
    "维修",
    "拆解",
    "报废",
    "垃圾佬",
    "捡漏",
    "伊拉克",
    "老款",
    "洋垃圾",
    "破烂",
    "尸体",
    "战损",
    "战损版",
    "成色差",
    "暗病",
    "仅拆封不保",
    "配件机",
    "通电不亮",
    "清仓处理二手",
    "下家",
    "修不好",
    "淘二手",
    "回收",
    "拆机",
    "故障",
)
NEGATIVE_OLD_WORDS_VI_EN = re.compile(
    r"\b(do\s+cu|hang\s+cu|2nd|secondhand|pass\s+lai|thanh\s+ly\s+cu|ve\s+chai|ra\s+xac|xac\s+may|sua\s+chua|hang\s+bai|do\s+nat|hong\s+hoc|thay\s+man|dong\s+may|tai\s+che|do\s+co|thanh\s+ly|hu\s+hong)\b",
    re.I,
)


def is_old_product(title):
    """Detect if title refers to used, second-hand, scrap, repair, or damaged items."""
    if not isinstance(title, str) or not title.strip():
        return False
    if any(w in title for w in NEGATIVE_OLD_WORDS_ZH):
        return True
    norm = unicodedata.normalize("NFKD", title.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in norm if not unicodedata.combining(c)).casefold()
    if NEGATIVE_OLD_WORDS_VI_EN.search(plain):
        return True
    return False


COMMERCIAL_ZH_WORDS = (
    "好物",
    "推荐",
    "测评",
    "评测",
    "开箱",
    "种草",
    "实测",
    "使用体验",
    "上手",
    "首发",
    "性价比",
    "带货",
    "购买",
    "沉浸式开箱",
    "日常分享",
    "同款",
    "选购",
    "避坑",
    "对比",
    "展示",
    "全新",
    "新品",
    "体验",
    "桌搭",
    "桌面搭配",
    "硬核测评",
    "数码好物",
    "闭眼入",
    "真香",
    "深度评测",
    "开箱体验",
    "开箱测评",
    "避坑指南",
    "质感",
    "沉浸式体验",
    "穿搭",
    "上身",
    "试穿",
    "变装",
    "跳舞",
    "舞蹈",
    "换装",
    "走秀",
    "沉浸式使用",
    "沉浸式",
    "使用教程",
    "教程",
    "日常使用",
    "日常vlog",
    "好物分享",
)
COMMERCIAL_VI_EN_WORDS = re.compile(
    r"\b(review|danh\s+gia|tren\s+tay|mo\s+hop|unboxing|trai\s+nghiem|gio\s+hang|shop|gia\s+re|chinh\s+hang|huong\s+dan|san\s+sale|deal|voucher|nen\s+mua|mua\s+ngay|link\s+mua|dat\s+mua|mua\s+hang|mua\s+tai|so\s+sanh|giam\s+gia|moi\s+tinh|hang\s+moi|dap\s+hop|mac\s+thu|len\s+do|phoi\s+do|nhay|dance|ootd|outfit|test|dung\s+thu|trai\s+nghiem\s+thuc\s+te|desk\s*setup|do\s+cong\s+nghe|phu\s+kien|tot\s+nhat|dang\s+mua)\b",
    re.I,
)


def commercial_intent(title):
    """Detect if title carries commercial, review, or product showcase intent."""
    if not isinstance(title, str) or not title.strip() or is_old_product(title):
        return False, 0
    zh_hits = sum(1 for w in COMMERCIAL_ZH_WORDS if w in title)
    norm = unicodedata.normalize("NFKD", title.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in norm if not unicodedata.combining(c)).casefold()
    vi_en_hits = len(COMMERCIAL_VI_EN_WORDS.findall(plain))
    hits = zh_hits + vi_en_hits
    if hits == 0:
        return False, 0
    return True, min(100, hits * 35)


def tokens(text):
    """Comparable words of a text: lower case, no accents or Vietnamese đ, brand aliases folded, runs of Chinese characters kept whole."""
    text = unicodedata.normalize("NFKD", normalized(text).replace("đ", "d"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9_]+|[㐀-鿿]+", text))


def _result(level, score, reason, evidence=(), commercial=False, commercial_score=0, is_old=False):
    return {
        "level": level,
        "score": score,
        "reason": reason,
        "evidence": list(evidence),
        "commercial": commercial,
        "commercial_score": commercial_score,
        "is_old": is_old,
    }


def _by_id(expected, found, title=""):
    same = expected == found
    reason = "Cùng mã sản phẩm" if same else "Khác mã sản phẩm"
    is_comm, comm_score = commercial_intent(title) if same else (False, 0)
    return _result(
        "id" if same else "different",
        100 if same else 0,
        reason + (" · Video bán hàng/review" if is_comm else ""),
        [{"facet": "Mã sản phẩm", "state": "ok" if same else "different", "value": found}],
        commercial=is_comm,
        commercial_score=comm_score,
    )


def _versions(text):
    return set(re.findall(r"(?<![a-z0-9])v\s*(\d+)(?![a-z0-9])", normalized(text)))


def _model_conflicts(model, title):
    """Another numbered model in the same line is ambiguous, even if the requested model is also mentioned."""
    pattern = r"(?<![a-z0-9])([a-z]{1,12})[\s-]+(\d{1,6})(?![a-z0-9])"
    wanted = set(re.findall(pattern, normalized(model)))
    found = set(re.findall(pattern, normalized(title)))
    lines = {line for line, number in wanted}
    return any(line in lines and (line, number) not in wanted for line, number in found)


def _model_codes(wanted, asked):
    """Words of the request with a digit in them (S24, ACE68, 15), except specifications."""
    return {t for t in wanted if any(c.isdigit() for c in t)} - set(SPEC.findall(normalized(asked)))


def _evidence(identity, facets, seen, soft):
    return [
        {
            "facet": label,
            "state": "ok" if facets[key] <= seen else ("unverified" if key in soft else "different"),
            "value": identity.get(key, ""),
        }
        for key, label in FACETS
        if facets[key] and key != "model"
    ]


def candidate_match(identity, item):
    """Recheck stored candidates under current rules without relaxing an earlier exclusion."""
    previous = item.get("match", {})
    if previous.get("level") == "different":
        return previous
    return match_identity(
        identity, item.get("title", ""), str(item.get("product_id") or "") if item.get("product_id_namespace") == "tiktok_shop" else ""
    )


def match_identity(identity, title, product_id=""):
    """How well a title fits the product asked for. The id decides when both have one. Otherwise: another brand, another model or an
    extra variant word EXCLUDES ('different'); words in common only make a 'candidate' for a person to check. An identity marked `soft`
    (read from a page title or a picture, not typed by the owner) never excludes on a model code or a variant it only guessed."""
    expected = str(identity.get("product_id") or "")
    if expected and product_id:
        return _by_id(expected, product_id, title)
    asked = identity.get("name") or identity.get("query", "")
    wanted, seen = tokens(asked), tokens(title)
    # Include Chinese category and feature terms from identity so Chinese video titles can match
    for zh_term in (identity.get("query_zh"), identity.get("category_zh")):
        if zh_term and isinstance(zh_term, str):
            wanted |= tokens(zh_term)
    for feat in identity.get("features_zh") or []:
        if isinstance(feat, str):
            wanted |= tokens(feat)

    facets = {key: tokens(identity.get(key, "")) for key, _ in FACETS}
    page = bool(identity.get("soft"))
    if not page:
        facets["model"] |= _model_codes(wanted, asked)
    soft = {"variant"} if identity.get("variant_soft") or page else set()
    evidence = _evidence(identity, facets, seen, soft)
    raw_title = title or ""

    if is_old_product(raw_title):
        return _result(
            "different",
            0,
            "Video về sản phẩm cũ/hàng bãi/sửa chữa; không phù hợp bán hàng mới",
            evidence,
            commercial=False,
            commercial_score=0,
            is_old=True,
        )

    # Check category conflict (e.g. keyboard vs mouse)
    cat_zh = identity.get("category_zh") or ""
    if cat_zh == "键盘" and "鼠标" in raw_title and "键盘" not in raw_title:
        return _result("different", 0, "Khác danh mục sản phẩm (chuột thay vì bàn phím)", evidence)
    if cat_zh == "鼠标" and "键盘" in raw_title and "鼠标" not in raw_title:
        return _result("different", 0, "Khác danh mục sản phẩm (bàn phím thay vì chuột)", evidence)

    # Exclude cross-industry noise when searching electronics & accessories
    is_electronics = identity.get("category") == "electronics" or cat_zh in (
        "数码配件",
        "电子产品",
        "数码好物 数码配件",
        "键盘",
        "鼠标",
        "耳机",
        "快充充电器",
        "充电宝",
        "支架",
        "拓展坞",
        "升降桌",
    )
    if is_electronics:
        cross_industry_words = (
            "连衣裙",
            "女装",
            "男装",
            "半身裙",
            "内衣",
            "睡衣",
            "口红",
            "眼影",
            "粉底液",
            "卸妆",
            "零食",
            "螺蛳粉",
            "方便面",
            "辣条",
            "纸尿裤",
            "奶粉",
            "宠物粮",
            "猫砂",
        )
        tech_words = (
            "数码",
            "外设",
            "桌搭",
            "键盘",
            "鼠标",
            "耳机",
            "充电",
            "支架",
            "拓展坞",
            "线",
            "电脑",
            "手机",
            "平板",
            "蓝牙",
            "快充",
            "升降桌",
        )
        if any(w in raw_title for w in cross_industry_words) and not any(w in raw_title for w in tech_words):
            return _result(
                "different", 0, "Khác danh mục ngành hàng (video thời trang/mỹ phẩm/thực phẩm, không khớp điện tử & phụ kiện)", evidence
            )

    # a title that does not say the brand is not another brand (it stays a candidate with a lower score); one that names another is
    if facets["brand"] and not facets["brand"] <= seen and seen & (KNOWN_BRANDS - facets["brand"]):
        return _result("different", 0, "Thương hiệu khác với thương hiệu đã xác định", evidence)
    if facets["variant"] and not facets["variant"] <= seen and "variant" not in soft:
        return _result("different", 0, "Chưa khớp biến thể đã xác định", evidence)
    model = facets["model"]
    if model and not page and _model_conflicts(identity.get("model", "") or asked, title):
        return _result("different", 0, "Tiêu đề nhắc model khác cùng dòng; không coi là đúng sản phẩm", evidence)
    if (model or page) and ((seen & VARIANT_WORDS) - wanted - facets["variant"] or _versions(title) - _versions(asked)):
        evidence.append({"facet": "Model", "state": "different", "value": identity.get("model") or " ".join(sorted(model))})
        return _result("different", 0, "Có biến thể khác với sản phẩm yêu cầu", evidence)
    if model and not page and (wanted & VARIANT_WORDS) - seen:
        evidence.append({"facet": "Model", "state": "different", "value": identity.get("model") or " ".join(sorted(model))})
        return _result("different", 0, "Thiếu biến thể bạn đã yêu cầu", evidence)
    if model:
        ok = model <= seen
        evidence.append({"facet": "Model", "state": "ok" if ok else "different", "value": identity.get("model") or " ".join(sorted(model))})
        if not ok:
            return _result("different", 0, "Chưa khớp model; không coi là đúng sản phẩm", evidence)
    if facets["brand"] and model:
        wanted = facets["brand"] | model | facets["variant"]
    if not wanted:
        return _result("unverified", 0, "Chưa có thông tin đối chiếu", evidence)

    matched_count = 0
    for w in wanted:
        if w in seen:
            matched_count += 1
        elif any("\u3400" <= c <= "\u9fff" for c in w) and w in raw_title:
            matched_count += 1
    score = round(100 * matched_count / len(wanted))
    is_comm, comm_score = commercial_intent(title)
    return _result(
        "candidate",
        score,
        "Khớp %d%% từ khóa%s; cần xem video và biến thể" % (score, " · Video bán hàng/review" if is_comm else ""),
        evidence,
        commercial=is_comm,
        commercial_score=comm_score,
    )
