"""The topics a video can have, and a free keyword guess used to pick candidates before downloading.

A topic is decided twice. Before download the source's own category (a Douyin tab, a TikTok chip; the browser agent knows their names)
and the keywords in the title give a cheap, noisy *hint* so the collector looks at, and downloads, what the accounts want. After the
video is analysed Gemini's answer is the truth, and the video goes to an account that accepts that topic.
"""

import re
from collections import namedtuple

Topic = namedtuple("Topic", "id vi gemini keywords")

OTHER = "other"  # never posted unless the owner overrides: news, politics, ads, shopping, medical advice...

TOPICS = (
    Topic(
        "music",
        "\u00c2m nh\u1ea1c v\u00e0 nh\u1ea3y",
        "singing, instrumental, live performance, dance and choreography, lip-sync",
        "\u97f3\u4e50|\u6b4c|\u5531|\u6f14\u5531\u4f1a|\u4e50\u961f|\u94a2\u7434|\u5409\u4ed6|\u67b6\u5b50\u9f13|\u5c0f\u63d0\u7434|\u7ffb\u5531|\u821e\u8e48|\u8df3\u821e|\u821e\u53f0|\u821e|cover|music|song|dance|live|nh\u1ea1c|h\xe1t",
    ),
    Topic(
        "comedy",
        "H\u00e0i h\u01b0\u1edbc, ti\u1ec3u ph\u1ea9m",
        "comedy sketches, pranks, funny situations, skits",
        "\u641e\u7b11|\u5267\u60c5|\u6574\u86ca|\u6076\u641e|\u5185\u5bb9\u8fc7\u4e8e\u771f\u5b9e|\u8ff7\u60d1\u884c\u4e3a|\u6bb5\u5b50|\u5c0f\u54c1|\u559c\u5267|\u6c99\u96d5|\u6574\u6d3b|\u53cd\u8f6c|\u540d\u573a\u9762|funny|comedy|skit|prank|h\xe0i",
    ),
    Topic(
        "pets",
        "Th\u00fa c\u01b0ng, \u0111\u1ed9ng v\u1eadt",
        "pets and animals",
        "\u732b|\u72d7|\u5ba0\u7269|\u840c\u5ba0|\u94f2\u5c4e\u5b98|\u52a8\u7269|\u718a\u732b|\u9e1f|\u6d77\u6d0b\u751f\u7269|pet|cat|dog|animal|m\xe8o|ch\xf3",
    ),
    Topic(
        "food",
        "\u1ea8m th\u1ef1c",
        "cooking, eating, restaurants, street food",
        "\u7f8e\u98df|\u597d\u5403|\u505a\u6cd5|\u98df\u8c31|\u83dc\u8c31|\u63a2\u5e97|\u706b\u9505|\u70e7\u70e4|\u65e9\u9910|\u5c0f\u5403|\u725b\u8089|\u9762\u6761|\u86cb\u7cd5|\u751c\u54c1|\u6599\u7406|\u70f9\u996a|\u5403\u8d27|food|recipe|cooking|\u0103n|n\u1ea5u",
    ),
    Topic(
        "travel",
        "Du l\u1ecbch, c\u1ea3nh \u0111\u1eb9p",
        "places, scenery, trips and travel",
        "\u65c5\u884c|\u65c5\u6e38|\u653b\u7565|\u81ea\u9a7e|\u666f\u70b9|\u6c11\u5bbf|\u623f\u8f66|\u6253\u5361|\u4e00\u65e5\u6e38|\u65c5\u9014|\u98ce\u666f|travel|trip|tour|du l\u1ecbch",
    ),
    Topic(
        "family",
        "Gia \u0111\u00ecnh, tr\u1ebb em",
        "children, babies, parenting and family moments",
        "\u5b9d\u5b9d|\u5e26\u5a03|\u80b2\u513f|\u4eb2\u5b50|\u840c\u5a03|\u5988\u5988|\u7238\u7238|\u5b69\u5b50|\u5a74\u513f|\u5e7c\u5d3d|\u5c0f\u670b\u53cb|\u5b9d\u5988|baby|kids|family|em b\xe9",
    ),
    Topic(
        "beauty",
        "L\u00e0m \u0111\u1eb9p, th\u1eddi trang",
        "makeup, fashion, outfits, hairstyle",
        "\u7f8e\u5986|\u5316\u5986|\u5986\u5bb9|\u7a7f\u642d|\u65f6\u5c1a|\u7f8e\u7532|\u62a4\u80a4|\u53d1\u578b|\u670d\u88c5|\u53d8\u88c5|outfit|makeup|beauty|fashion|l\xe0m \u0111\u1eb9p",
    ),
    Topic(
        "sports",
        "Th\u1ec3 thao",
        "sports, fitness, fishing, billiards",
        "\u4f53\u80b2|\u8db3\u7403|\u7bee\u7403|\u4e52\u4e53|\u53f0\u7403|\u65af\u8bfa\u514b|\u7fbd\u6bdb\u7403|\u7f51\u7403|\u5065\u8eab|\u8def\u4e9a|\u9493\u9c7c|\u6bd4\u8d5b|\u5965\u8fd0|nba|sport|fitness|b\xf3ng",
    ),
    Topic(
        "gaming",
        "Game",
        "video games and e-sports",
        r"游戏|王者|吃鸡|和平精英|原神|手游|电竞|英雄联盟|三角洲|暗区|崩坏|米哈游|game|gaming",
    ),
    Topic(
        "anime",
        "Ho\u1ea1t h\u00ecnh, anime",
        "anime, cartoons, comics, cosplay",
        "\u52a8\u6f2b|\u4e8c\u6b21\u5143|\u52a8\u753b|\u56fd\u6f2b|\u6f2b\u753b|cosplay|anime|manga|ho\u1ea1t h\xecnh",
    ),
    Topic(
        "movies",
        "Phim, tr\u00edch \u0111o\u1ea1n",
        "film and TV clips, drama, show highlights",
        r"电影|影视|电视剧|追剧|解说|综艺|预告|港片|剧集|悬疑|票房|movie|film|series|phim",
    ),
    Topic(
        "lifestyle",
        "\u0110\u1eddi s\u1ed1ng, vlog, m\u1eb9o v\u1eb7t",
        "daily life, vlog, home, DIY, crafts, life hacks",
        "vlog|\u65e5\u5e38|\u5bb6\u5c45|\u6539\u9020|\u6536\u7eb3|\u597d\u7269|\u6574\u7406|\u5f00\u7bb1|diy|\u624b\u5de5|\u6e05\u6d01|\u5c0f\u5999\u62db|\u9732\u8425|lifestyle|m\u1eb9o",
    ),
    Topic(
        "knowledge",
        "Ki\u1ebfn th\u1ee9c, khoa h\u1ecdc",
        "science, facts, history, education, tutorials, technology and gadget reviews",
        "\u79d1\u666e|\u77e5\u8bc6|\u51b7\u77e5\u8bc6|\u5e72\u8d27|\u5386\u53f2|\u77e5\u8bc6\u70b9|\u6559\u5b66|science|learn|howto|ki\u1ebfn th\u1ee9c",
    ),
    Topic(
        "news",
        "Tin n\u00f3ng, x\u00e3 h\u1ed9i, drama",
        "breaking news, current events, politics, social controversy, scandals, conflict and drama caught on camera",
        "\u65b0\u95fb|\u70ed\u641c|\u5435\u67b6|\u51b2\u7a81|\u4e8b\u4ef6|\u4e89\u8bae|\u7a81\u53d1|\u8b66\u65b9|\u901a\u62a5|\u7ef4\u6743|news|scandal|drama|tin n\xf3ng",
    ),
    Topic(
        "entertainment",
        "Gi\u1ea3i tr\u00ed t\u1ed5ng h\u1ee3p",
        "any other harmless fun content that fits no category above: talent, challenges, cute moments",
        r"",
    ),
)

# the hashtag a viewer of that topic searches for (Vietnamese, no accents): the fallback when the model suggests too few tags
TOPIC_TAGS = {
    "music": "nhac",
    "comedy": "haihuoc",
    "pets": "thucung",
    "food": "amthuc",
    "travel": "dulich",
    "family": "giadinh",
    "beauty": "lamdep",
    "sports": "thethao",
    "gaming": "game",
    "anime": "anime",
    "movies": "phim",
    "lifestyle": "doisong",
    "knowledge": "kienthuc",
    "news": "tinnong",
    "entertainment": "giaitri",
}
TOPIC_IDS = tuple(t.id for t in TOPICS)
TOPIC_LABEL = {t.id: t.vi for t in TOPICS}
BY_ID = {t.id: t for t in TOPICS}
# what the single account of 1.0 - 1.3 accepted, spelled out in the finer topics (it used to be "entertainment" and "music")
LEGACY_TOPICS = ("entertainment", "music", "comedy", "pets", "family", "lifestyle")
# what a new account takes by default: the old topics plus hot news and drama (the owner wants the most talked-about content)
DEFAULT_TOPICS = (*LEGACY_TOPICS, "news")
_CJK = re.compile("[\u3400-\u9fff]")
_LETTER = "A-Za-z0-9\u00c0-\u024f\u1e00-\u1eff"  # Latin and Vietnamese letters; Chinese characters are deliberately not "letters" here


def _compile(keywords):
    """Chinese keywords match anywhere (Chinese has no spaces); Latin and Vietnamese ones only as whole words, so that 'cat' is not
    found in 'location', 'live' in 'deliver' or 'eat' in 'Livestock'. Hashtags glued to Chinese text ('#vlog日常') still match."""
    words = keywords.split("|")
    chinese = [w for w in words if _CJK.search(w)]
    others = [w for w in words if not _CJK.search(w)]
    parts = []
    if chinese:
        parts.append("(?:%s)" % "|".join(chinese))
    if others:
        parts.append("(?<![%s])(?:%s)(?![%s])" % (_LETTER, "|".join(others), _LETTER))
    return re.compile("|".join(parts), re.I)


_KEYWORDS = {t.id: _compile(t.keywords) for t in TOPICS if t.keywords}


def label(topic):
    return TOPIC_LABEL.get(topic) or ("Ngo\u00e0i ch\u1ee7 \u0111\u1ec1" if topic == OTHER else (topic or "ch\u01b0a r\u00f5"))


def valid_topics(topics):
    """A clean, ordered, duplicate-free list of known topic ids, or ValueError."""
    if not isinstance(topics, (list, tuple)) or not topics or len(topics) > len(TOPIC_IDS):
        raise ValueError("Ch\u1ecdn \u00edt nh\u1ea5t m\u1ed9t ch\u1ee7 \u0111\u1ec1")
    unknown = [t for t in topics if t not in TOPIC_IDS]
    if unknown:
        raise ValueError("Ch\u1ee7 \u0111\u1ec1 kh\u00f4ng c\u00f3 trong danh s\u00e1ch: %s" % ", ".join(map(str, unknown))[:80])
    return [t for t in TOPIC_IDS if t in topics]


def guess_topics(text):
    """Topics whose keywords occur in the title or hashtags, most hits first. Empty when nothing matches. A hint, never a verdict."""
    hits = {topic: len(rx.findall(text or "")) for topic, rx in _KEYWORDS.items()}
    return sorted((t for t, n in hits.items() if n), key=lambda t: -hits[t])


def topic_hint(stream_topic, text):
    """Best guess before download. The source's own category wins unless the title clearly says something else (two or more keyword
    hits for another topic); with no category the strongest keyword wins; with neither there is no hint (None)."""
    guessed = guess_topics(text)
    if stream_topic:
        if guessed and guessed[0] != stream_topic and stream_topic not in guessed:
            other = guessed[0]
            if len(_KEYWORDS[other].findall(text or "")) >= 2:
                return other
        return stream_topic
    return guessed[0] if guessed else None


def prompt_lines():
    """The topic menu inside the analysis prompt, one line per topic."""
    return "\n".join('   - "%s": %s' % (t.id, t.gemini) for t in TOPICS)
