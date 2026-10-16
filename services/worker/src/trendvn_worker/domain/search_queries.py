"""Preserve user identifiers and build bounded language-specific queries, without guessing a model from a photo."""

import re
import unicodedata

BRAND_ALIASES = {
    "迈从": "mchose",
    "小米": "xiaomi",
    "三星": "samsung",
    "苹果": "apple",
    "雷蛇": "razer",
    "罗技": "logitech",
    "华为": "huawei",
    "欧珀": "oppo",
    "维沃": "vivo",
    "索尼": "sony",
    "华硕": "asus",
    "联想": "lenovo",
    "戴尔": "dell",
    "惠普": "hp",
    "渴创": "keychron",
    "艾酷": "akko",
    "安克": "anker",
    "倍思": "baseus",
    "绿联": "ugreen",
    "飞利浦": "philips",
    "杰宝": "jbl",
}
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
    (r"\btai\s+nghe\b|\bheadphones?\b|\bearphones?\b|耳机", "headphones", "耳机"),
    (r"\bpin\s+(?:sạc\s+)?dự\s+phòng\b|\bpowerbank\b|充电宝", "powerbank", "充电宝"),
    (r"\bgiá\s+đỡ\b|\bchân\s+đế\b|\bstand\b|支架", "stand", "支架"),
    (r"\bhub\b|\bdock\b|\bcổng\s+chuyển\b|拓展坞", "hub", "拓展坞"),
    (r"\bbàn\s+nâng\s+hạ\b|升降桌", "desk", "升降桌"),
    (r"\bđồng\s+hồ\b|\bwatch\b|手表", "smartwatch", "智能手表"),
    (r"\bloa\b|\bspeaker\b|音箱|音响", "speaker", "蓝牙音箱"),
    (r"\bốp\s+lưng\b|\bcase\b|手机壳", "phone_case", "手机壳"),
    (r"\bcáp\s+sạc\b|\bcủ\s+sạc\b|\bsạc\b|\bcharger\b|充电器|快充", "charger", "快充充电器"),
    (r"\bmàn\s+hình\b|\bmonitor\b|\bdisplay\b|显示器", "monitor", "显示器"),
    (r"\bmáy\s+tính\s+bảng\b|\btablet\b|\bipad\b|平板", "tablet", "平板电脑"),
    (r"\bmáy\s+tính\b|\blaptop\b|电脑|笔记本", "laptop", "笔记本电脑"),
    (r"\bđiện\s+thoại\b|\bphone\b|\bsmartphone\b|手机", "phone", "智能手机"),
    (r"\bmáy\s+cạo\s+râu\b|\bshaver\b|剃须刀", "shaver", "电动剃须刀"),
    (r"\bmáy\s+sấy\s+tóc\b|\bhair\s*dryer\b|吹风机", "hair_dryer", "电吹风"),
    (r"\bbình\s+giữ\s+nhiệt\b|\bthermos\b|保温杯", "thermos", "保温杯"),
    (r"\bnồi\s+chiên\b|\bair\s*fryer\b|空气炸锅", "air_fryer", "空气炸锅"),
    (r"\bquạt\b|\bfan\b|风扇", "fan", "风扇"),
    (r"\bđèn\b|\blamp\b|\bled\b|台灯", "lamp", "台灯"),
    (r"\bmáy\s+hút\s+bụi\b|\brobot\s+hút\s+bụi\b|\bvacuum\b|吸尘器|扫地机", "vacuum", "扫地机器人"),
    (r"\bgiày\b|\bshoes?\b|\bsneakers?\b|鞋", "shoes", "运动鞋"),
    (r"\báo\b|\bshirt\b|\bt-?shirt\b|\bjacket\b|衣服|T恤", "clothes", "衣服"),
    (r"\bquần\b|\bpants?\b|裤子", "pants", "裤子"),
    (r"\btúi\s+xách\b|\bbalo\b|\bbackpack\b|\bbag\b|背包|包包", "bag", "双肩包"),
    (r"\bmỹ\s+phẩm\b|\bson\s+môi\b|\bkem\b|美妆|口红", "cosmetics", "美妆护肤"),
    (r"\bđồ\s+chơi\b|\btoy\b|玩具", "toy", "玩具"),
)
FEATURE_ZH = (
    (r"\bkhông\s+dây\b|\bwireless\b", "无线"),
    (r"\bchống\s+ồn\b|\banc\b|\bnoise\s+cancelling\b", "降噪"),
    (r"\bcơ\b|\bmechanical\b", "机械"),
    (r"\btừ\s+trục\b|\bmagnetic\b", "磁轴"),
    (r"\bgaming\b|\bchơi\s+game\b", "电竞"),
    (r"\bbluetooth\b", "蓝牙"),
    (r"\bthông\s+minh\b|\bsmart\b", "智能"),
    (r"\bnhanh\b|\bquick\b|\bfast\b", "快充"),
    (r"\bgan\b|\bchất\s+bán\s+dẫn\b", "氮化镓"),
    (r"\bdesk\s*setup\b|\bbàn\s+làm\s+việc\b", "桌搭"),
)
NOT_CHINESE_NOR_PLAIN = re.compile(r"[^\x00-\x7f\u3000-\u9fff\uff00-\uffef]")


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
    features_zh = [zh for pat, zh in FEATURE_ZH if re.search(pat, text, re.I)]
    return {
        "name": name,
        "query": query,
        "brand": brand,
        "model": " ".join(models).upper(),
        "variant": " ".join(re.findall(r"\b(?:air|turbo|gt|v\d+)\b", query, re.I)),
        "category": category,
        "category_zh": category_zh,
        "features_zh": features_zh,
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
        features = " ".join(identity.get("features_zh") or [])
        parts = [translated_brand or identity.get("brand", ""), model, identity.get("variant", ""), features, category]
        zh = " ".join(filter(None, parts)) if (model or translated_brand or category or features) else ""
        if not zh and not NOT_CHINESE_NOR_PLAIN.search(query):
            zh = query
    if zh and NOT_CHINESE_NOR_PLAIN.search(zh):
        zh = re.sub(NOT_CHINESE_NOR_PLAIN, " ", zh)
        zh = " ".join(zh.split())
    return {"tiktok": query[:160], "douyin": zh[:160]}
