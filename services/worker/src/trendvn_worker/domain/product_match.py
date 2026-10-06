"""Does a title, or a product id, belong to the product the owner asked for? Labels are evidence, never a probability: a model that does
not match excludes a candidate even when most keywords overlap, and keyword overlap alone is only ever a 'candidate' for a person to check.
"""

import re
import unicodedata

from .search_queries import normalized

# Words that make another product of the same model number ("Galaxy S24" and "Galaxy S24 Ultra"): a title carrying one the owner did not
# ask for is a different product.
VARIANT_WORDS = {"ultra", "pro", "max", "plus", "mini", "lite", "fe", "air", "turbo", "gt", "v2"}
FACETS = (("brand", "Thương hiệu"), ("model", "Model"), ("variant", "Biến thể"))


def tokens(text):
    """Comparable words of a text: lower case, no accents or Vietnamese đ, brand aliases folded, runs of Chinese characters kept whole."""
    text = unicodedata.normalize("NFKD", normalized(text).replace("đ", "d"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9_]+|[㐀-鿿]+", text))


def _result(level, score, reason, evidence=()):
    return {"level": level, "score": score, "reason": reason, "evidence": list(evidence)}


def _by_id(expected, found):
    same = expected == found
    reason = "Cùng mã sản phẩm" if same else "Khác mã sản phẩm"
    return _result(
        "id" if same else "different",
        100 if same else 0,
        reason,
        [{"facet": "Mã sản phẩm", "state": "ok" if same else "different", "value": found}],
    )


def _versions(text):
    return set(re.findall(r"\bv\s*(\d+)\b", normalized(text)))


def match_identity(identity, title, product_id=""):
    expected = str(identity.get("product_id") or "")
    if expected and product_id:
        return _by_id(expected, product_id)
    asked = identity.get("name") or identity.get("query", "")
    wanted, seen = tokens(asked), tokens(title)
    facets = {key: tokens(identity.get(key, "")) for key, _ in FACETS}
    facets["model"] |= {t for t in wanted if any(c.isdigit() for c in t)}  # a word with a digit in it is a model code
    evidence = [
        {"facet": label, "state": "ok" if facets[key] <= seen else "different", "value": identity.get(key, "")}
        for key, label in FACETS
        if facets[key] and key != "model"
    ]
    if facets["brand"] and not facets["brand"] <= seen:
        return _result("different", 0, "Chưa khớp thương hiệu đã xác định", evidence)
    if facets["variant"] and not facets["variant"] <= seen:
        return _result("different", 0, "Chưa khớp biến thể đã xác định", evidence)
    model = facets["model"]
    if model and ((seen & VARIANT_WORDS) - wanted - facets["variant"] or _versions(title) - _versions(asked)):
        evidence.append({"facet": "Model", "state": "different", "value": identity.get("model") or " ".join(sorted(model))})
        return _result("different", 0, "Có biến thể khác với sản phẩm yêu cầu", evidence)
    if model:
        ok = model <= seen
        evidence.append({"facet": "Model", "state": "ok" if ok else "different", "value": identity.get("model") or " ".join(sorted(model))})
        if not ok:
            return _result("different", 0, "Chưa khớp model; không coi là đúng sản phẩm", evidence)
    if facets["brand"] and model:
        wanted = facets["brand"] | model | facets["variant"]
    if not wanted:
        return _result("unverified", 0, "Chưa có thông tin đối chiếu", evidence)
    score = round(100 * len(wanted & seen) / len(wanted))
    return _result("candidate", score, "Khớp %d%% từ khóa; cần xem video và biến thể" % score, evidence)
