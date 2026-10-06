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


def match_identity(identity, title, product_id=""):
    """How well a title fits the product asked for. The id decides when both have one. Otherwise: another brand, another model or an
    extra variant word EXCLUDES ('different'); words in common only make a 'candidate' for a person to check. An identity marked `soft`
    (read from a page title or a picture, not typed by the owner) never excludes on a model code or a variant it only guessed."""
    expected = str(identity.get("product_id") or "")
    if expected and product_id:
        return _by_id(expected, product_id)
    asked = identity.get("name") or identity.get("query", "")
    wanted, seen = tokens(asked), tokens(title)
    facets = {key: tokens(identity.get(key, "")) for key, _ in FACETS}
    page = bool(identity.get("soft"))
    if not page:
        facets["model"] |= _model_codes(wanted, asked)
    soft = {"variant"} if identity.get("variant_soft") or page else set()
    evidence = _evidence(identity, facets, seen, soft)
    # a title that does not say the brand is not another brand (it stays a candidate with a lower score); one that names another is
    if facets["brand"] and not facets["brand"] <= seen and seen & (KNOWN_BRANDS - facets["brand"]):
        return _result("different", 0, "Thương hiệu khác với thương hiệu đã xác định", evidence)
    if facets["variant"] and not facets["variant"] <= seen and "variant" not in soft:
        return _result("different", 0, "Chưa khớp biến thể đã xác định", evidence)
    model = facets["model"]
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
    score = round(100 * len(wanted & seen) / len(wanted))
    return _result("candidate", score, "Khớp %d%% từ khóa; cần xem video và biến thể" % score, evidence)
