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
        "Âm nhạc và nhảy",
        "singing, instrumental, live performance, dance and choreography, lip-sync",
        r"音乐|歌|唱|演唱会|乐队|钢琴|吉他|架子鼓|小提琴|翻唱|舞蹈|跳舞|舞台|舞|cover|music|song|dance|live|nhạc|hát",
    ),
    Topic(
        "comedy",
        "Hài hước, tiểu phẩm",
        "comedy sketches, pranks, funny situations, skits",
        r"搞笑|剧情|整蛊|恶搞|内容过于真实|迷惑行为|段子|小品|喜剧|沙雕|整活|反转|名场面|funny|comedy|skit|prank|hài",
    ),
    Topic(
        "pets",
        "Thú cưng, động vật",
        "pets and animals",
        r"猫|狗|宠物|萌宠|铲屎官|动物|熊猫|鸟|海洋生物|pet|cat|dog|animal|mèo|chó",
    ),
    Topic(
        "food",
        "Ẩm thực",
        "cooking, eating, restaurants, street food",
        r"美食|好吃|做法|食谱|菜谱|探店|火锅|烧烤|早餐|小吃|牛肉|面条|蛋糕|甜品|料理|烹饪|吃货|food|recipe|cooking|ăn|nấu",
    ),
    Topic(
        "travel",
        "Du lịch, cảnh đẹp",
        "places, scenery, trips and travel",
        r"旅行|旅游|攻略|自驾|景点|民宿|房车|打卡|一日游|旅途|风景|travel|trip|tour|du lịch",
    ),
    Topic(
        "family",
        "Gia đình, trẻ em",
        "children, babies, parenting and family moments",
        r"宝宝|带娃|育儿|亲子|萌娃|妈妈|爸爸|孩子|婴儿|幼崽|小朋友|宝妈|baby|kids|family|em bé",
    ),
    Topic(
        "beauty",
        "Làm đẹp, thời trang",
        "makeup, fashion, outfits, hairstyle",
        r"美妆|化妆|妆容|穿搭|时尚|美甲|护肤|发型|服装|变装|outfit|makeup|beauty|fashion|làm đẹp",
    ),
    Topic(
        "sports",
        "Thể thao",
        "sports, fitness, fishing, billiards",
        r"体育|足球|篮球|乒乓|台球|斯诺克|羽毛球|网球|健身|路亚|钓鱼|比赛|奥运|nba|sport|fitness|bóng",
    ),
    Topic(
        "gaming",
        "Game",
        "video games and e-sports",
        r"游戏|王者|吃鸡|和平精英|原神|手游|电竞|英雄联盟|三角洲|暗区|崩坏|米哈游|game|gaming",
    ),
    Topic(
        "anime",
        "Hoạt hình, anime",
        "anime, cartoons, comics, cosplay",
        r"动漫|二次元|动画|国漫|漫画|cosplay|anime|manga|hoạt hình",
    ),
    Topic(
        "movies",
        "Phim, trích đoạn",
        "film and TV clips, drama, show highlights",
        r"电影|影视|电视剧|追剧|解说|综艺|预告|港片|剧集|悬疑|票房|movie|film|series|phim",
    ),
    Topic(
        "lifestyle",
        "Đời sống, vlog, mẹo vặt",
        "daily life, vlog, home, DIY, crafts, life hacks",
        r"vlog|日常|家居|改造|收纳|好物|整理|开箱|diy|手工|清洁|小妙招|露营|lifestyle|mẹo",
    ),
    Topic(
        "knowledge",
        "Kiến thức, khoa học",
        "science, facts, history, education, tutorials, technology and gadget reviews",
        r"科普|知识|冷知识|干货|历史|知识点|教学|science|learn|howto|kiến thức",
    ),
    Topic(
        "news",
        "Tin nóng, xã hội, drama",
        "breaking news, current events, politics, social controversy, scandals, conflict and drama caught on camera",
        r"新闻|热搜|吵架|冲突|事件|争议|突发|警方|通报|维权|news|scandal|drama|tin nóng",
    ),
    Topic(
        "entertainment",
        "Giải trí tổng hợp",
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
    found in 'location', 'live' in 'deliver' or 'ăn' in 'Chăn nuôi'. Hashtags glued to Chinese text ('#vlog日常') still match."""
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
    return TOPIC_LABEL.get(topic) or ("Ngoài chủ đề" if topic == OTHER else (topic or "chưa rõ"))


def valid_topics(topics):
    """A clean, ordered, duplicate-free list of known topic ids, or ValueError."""
    if not isinstance(topics, (list, tuple)) or not topics or len(topics) > len(TOPIC_IDS):
        raise ValueError("Chọn ít nhất một chủ đề")
    unknown = [t for t in topics if t not in TOPIC_IDS]
    if unknown:
        raise ValueError("Chủ đề không có trong danh sách: %s" % ", ".join(map(str, unknown))[:80])
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
