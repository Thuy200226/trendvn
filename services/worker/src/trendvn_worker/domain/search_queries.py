"""Preserve user identifiers and build bounded language-specific queries, without guessing a model from a photo."""

import re
import unicodedata

BRAND_ALIASES = {"迈从": "mchose", "小米": "xiaomi", "三星": "samsung", "苹果": "apple", "雷蛇": "razer", "罗技": "logitech"}
# The word Chinese shops use for a product line, when it is more specific than the category: (brand, model pattern, Chinese category).
# Adding a product line is adding a row. MCHOSE ACE68: official manual file.maicong.cn/uploads/25/02/MCHOSE%2020250211.pdf
LINE_HINTS = (("mchose", r"ace\s*68", "磁轴键盘"),)
BRAND_ZH = {value: key for key, value in BRAND_ALIASES.items()}
# A number with its unit is a specification (256GB, 5000mAh, 5G), not part of a model's name.
SPEC_UNITS = "gb|tb|mah|hz|khz|inch|mm|cm|ml|kg|mp|fps|w|v|g|k"
SPEC_RAW = re.compile(r"(?<![A-Za-z0-9])\d+\s*(?:%s)(?![A-Za-z0-9])" % SPEC_UNITS, re.I)
# Brands a title may carry instead of the one asked for: with one of these in a title that lacks the asked brand it is another product.
KNOWN_BRANDS = frozenset(BRAND_ALIASES.values()) | {
    "huawei", "oppo", "vivo", "realme", "sony", "lg", "asus", "acer", "dell", "hp", "lenovo", "jbl", "anker", "baseus", "ugreen", "philips",
    "panasonic", "nokia", "motorola", "oneplus", "honor", "google", "microsoft", "nintendo", "keychron", "akko", "ducky", "corsair", "steelseries",
}  # fmt: skip
CATEGORIES = (
    (r"\bbàn\s+phím\b|\bkeyboard\b|键盘", "keyboard", "键盘"),
    (r"\bchuột\b|\bmouse\b|鼠标", "mouse", "鼠标"),
    (r"\btai\s+nghe\b|\bheadphones?\b|耳机", "headphones", "耳机"),
)


def normalized(text):
    text = unicodedata.normalize("NFKC", str(text)).casefold()  # fullwidth letters and digits become plain ones before anything is split
    text = text.replace("+", " plus ")
    for zh, latin in BRAND_ALIASES.items():
        text = text.replace(zh, " " + latin + " ")
    text = re.sub(r"([a-z])(?=\d)", r"\1 ", text)
    text = re.sub(r"(\d)(?=[a-z])", r"\1 ", text)
    return text


def explicit(text):
    """A short user description is authoritative even when an image model guesses something else."""
    if not text or len(text) > 160 or "https://" in text:
        return None
    name, category, category_zh = text.strip(), "", ""
    query = name
    for pattern, en, zh in CATEGORIES:
        if re.search(pattern, query, re.I):
            category, category_zh = en, zh
            query = re.sub(pattern, " ", query, flags=re.I)
            break
    query = " ".join(query.split()) or name
    folded = normalized(query)
    brand = next(
        (
            b.upper() if b in ("mchose", "lg", "hp", "jbl") else b.title()
            for b in sorted(KNOWN_BRANDS)
            if re.search(r"\b" + b + r"\b", folded)
        ),
        "",
    )
    models = re.findall(
        r"(?<![A-Za-z0-9])([A-Za-z]{1,12}[ -]?\d{1,6}(?:[A-Za-z]{1,4}\d{1,3})?[A-Za-z]{0,4})(?![A-Za-z0-9])", SPEC_RAW.sub(" ", query)
    )
    return {
        "name": name,
        "query": query,
        "brand": brand,
        "model": " ".join(models).upper(),
        "variant": " ".join(re.findall(r"\b(?:air|turbo|gt|v\d+)\b", query, re.I)),
        "category": category,
        "category_zh": category_zh,
        "uncertainty": "Cần xem video để xác minh sản phẩm",
    }


def query_plan(identity):
    query = identity.get("query") or identity.get("name", "")
    brand = identity.get("brand", "").casefold()
    zh = identity.get("query_zh", "")
    identifiers = " ".join(identity.get(k, "") for k in ("brand", "model", "variant"))
    # A translated query must retain every explicit identifier.
    required = set(re.findall(r"[a-z0-9]+", normalized(identifiers)))
    translated = set(re.findall(r"[a-z0-9]+", normalized(zh)))
    if zh and not required <= translated:
        zh = ""
    if not zh:
        translated_brand = BRAND_ZH.get(brand, "")
        model = identity.get("model", "")
        category = next(
            (zh for b, pattern, zh in LINE_HINTS if b == brand and re.search(pattern, model, re.I)), identity.get("category_zh", "")
        )
        zh = (
            " ".join(filter(None, (translated_brand or identity.get("brand", ""), model, identity.get("variant", ""), category)))
            if model and translated_brand
            else query
        )
    return {"tiktok": query[:160], "douyin": zh[:160]}
