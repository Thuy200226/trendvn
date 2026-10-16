"""Videos found from a chat answer: ranking against the product, and the owner's explicit pick into the processing queue, pinned to
the account the owner chose."""

import json
from ..domain.product_binding import catalog_binding
import re
import time
import uuid

from ..domain.platforms import canonical_url, COUNTRIES
from ..domain.product_match import match_identity, candidate_match
from ..jsonsafe import loads

MAX_RESULTS = 20

TOP_SALES_CATALOG = {
    "electronics": [
        ("Bàn phím cơ MCHOSE ACE68", "MCHOSE", "ACE68", "迈从 ACE68 磁轴键盘 测评 开箱"),
        ("Chuột không dây Logitech GPW", "Logitech", "GPW", "罗技 GPW 无线鼠标 测评"),
        ("Ốp lưng iPhone chống sốc thời trang", "Apple", "iPhone Case", "苹果 手机壳 开箱 测评 好物"),
        ("Tai nghe chống ồn Sony WH-1000XM5", "Sony", "WH-1000XM5", "索尼 WH-1000XM5 降噪耳机 测评"),
        ("Củ sạc nhanh GaN Anker 65W", "Anker", "65W GaN", "安克 65W 氮化镓快充 测评"),
        ("Pin sạc dự phòng Baseus 20000mAh", "Baseus", "20000mAh", "倍思 20000mAh 充电宝 开箱"),
        ("Vòng đeo tay thông minh Xiaomi Band 9", "Xiaomi", "Band 9", "小米手环9 体验 测评"),
        ("Đèn treo màn hình chống mỏi mắt Mijia", "Mijia", "Monitor Light Bar", "米家 屏幕挂灯 桌搭 开箱"),
        ("Micro thu âm không dây DJI Mic 2", "DJI", "Mic 2", "大疆 DJI Mic 2 无线麦克风 测评"),
        ("Hub chuyển đổi Type-C 7 trong 1 Ugreen", "Ugreen", "7in1 Hub", "绿联 Type-C 拓展坞 开箱"),
        ("Quạt tản nhiệt điện thoại sò lạnh từ tính", "BlackShark", "Cooler", "手机散热器 磁吸 测评"),
        ("Giá đỡ điện thoại kim loại để bàn xoay 360", "Baseus", "Metal Stand", "手机支架 金属 桌面 好物"),
    ],
    "beauty": [
        ("Toner chứa 2% BHA Obagi Clenziderm", "Obagi", "BHA 2%", "欧邦琪 2% 水杨酸 爽肤水 测评 开箱"),
        ("Serum Hyaluronic Acid Torriden Dive In 50ml", "Torriden", "Dive In Serum", "Torriden 玻尿酸 精华 测评 开箱"),
        ("Kem chống nắng kiềm dầu Anessa Perfect UV", "Anessa", "Sunscreen", "安耐晒 防晒霜 测评 美妆 种草"),
        ("Máy sấy tóc ion âm tốc độ cao Laifen", "Laifen", "High Speed Dryer", "徕芬 高速负离子吹风机 开箱 测评"),
        ("Máy rửa mặt sóng âm siêu sạch Foreo Luna", "Foreo", "Cleanser", "斐珞尔 声波洁面仪 护肤 好物"),
        ("Tinh chất phục hồi làm dịu da La Roche-Posay B5", "La Roche-Posay", "B5 Serum", "理肤泉 B5 精华 修复 测评"),
        ("Son dưỡng môi có màu DHC Lip Cream", "DHC", "Lip Cream", "DHC 润唇膏 测评 种草"),
        ("Nước tẩy trang Bioderma Sensibio H2O", "Bioderma", "Micellar Water", "贝德玛 卸妆水 测评 好物"),
    ],
    "fashion": [
        ("The Bad God Set Áo Quần Sweater Serenity", "The Bad God", "Sweater Set", "卫衣 套装 穿搭 测评 开箱"),
        ("Áo khoác gió chống nước thể thao Camel", "Camel", "Windbreaker", "骆驼 户外冲锋衣 穿搭 测评"),
        ("Giày chạy bộ đế êm thoáng khí Anta", "Anta", "Running Shoes", "安踏 透气缓震跑鞋 开箱 上脚"),
        ("Balo laptop chống trộm đa năng Mark Ryden", "Mark Ryden", "Backpack", "多功能双肩包 商务 测评"),
        ("Mũ lưỡi trai phong cách tối giản MLB", "MLB", "Baseball Cap", "棒球帽 穿搭 种草 开箱"),
        ("Quần ống rộng cạp cao tôn dáng Ulzzang", "Ulzzang", "Wide Leg Pants", "阔腿裤 显高显瘦 穿搭 测评"),
    ],
    "home": [
        ("Nước Xả Vải Đậm Đặc Hygiene 3L", "Hygiene", "Fabric Softener 3L", "柔顺剂 开箱 家用 好物"),
        ("Sữa tắm Lifebuoy Thiên nhiên Detox Chăm Sóc Da", "Lifebuoy", "Detox Body Wash", "沐浴露 测评 种草 好物"),
        ("Máy hút bụi cầm tay không dây Midea", "Midea", "Handheld Vacuum", "无线手持吸尘器 家居 好物"),
        ("Nồi chiên không dầu dung tích lớn Joyoung", "Joyoung", "Air Fryer", "空气炸锅 美食 测评 开箱"),
        ("Robot hút bụi lau nhà tự giặt giẻ Dreame", "Dreame", "Robot Vacuum", "追觅 扫地机器人 智能家居 实测"),
        ("Máy lọc không khí thông minh Xiaomi Air Purifier", "Xiaomi", "Air Purifier", "小米 空气净化器 体验"),
        ("Bình giữ nhiệt Lock&Lock 800ml inox 316", "Lock&Lock", "Thermos 800ml", "保温杯 大容量 好物 测评"),
    ],
    "food": [
        ("Thanh hạt dinh dưỡng ngũ cốc ăn kiêng Be&Cheery", "Be&Cheery", "Cereal Bar", "坚果谷物棒 美食 种草"),
        ("Trà thảo mộc thanh lọc giải nhiệt Tong Ren Tang", "Tong Ren Tang", "Herbal Tea", "草本养生茶 养生 测评"),
        ("Khô bò miếng sốt mật ong cay giòn", "FoodVN", "Beef Jerky", "牛肉干 零食 测评 开箱"),
        ("Bột matcha nguyên chất hữu cơ Nhật Bản", "Matcha", "Pure Powder", "纯抹茶粉 烘焙 饮品 测评"),
        ("Hạt điều rang muối vỏ lụa nguyên hạt", "Cashew", "Roasted Cashew", "腰果 坚果 零食 种草"),
    ],
    "sports": [
        ("Bình giữ nhiệt thể thao 1000ml Tomic", "Tomic", "Sports Bottle", "运动保温杯 健身 好物"),
        ("Thảm tập yoga chống trượt cao cấp Keep", "Keep", "Yoga Mat", "防滑瑜伽垫 居家 运动"),
        ("Dây kháng lực tập mông đùi đa năng PowerBand", "PowerBand", "Resistance Band", "弹力带 健身 居家 训练"),
        ("Con lăn tập cơ bụng lò xo trợ lực tự động", "AbRoller", "Ab Roller", "健腹轮 自动回弹 健身 测评"),
    ],
    "pets": [
        ("Máy cho thú cưng ăn tự động có camera Petkit", "Petkit", "Feeder", "自动宠物喂食器 萌宠 开箱"),
        ("Máy lọc nước tự động cho mèo Petkit", "Petkit", "Water Fountain", "猫咪自动饮水机 萌宠 好物"),
        ("Cát vệ sinh cho mèo đất sét khử mùi Bentonite", "Cature", "Cat Litter", "膨润土猫砂 结团 无尘 测评"),
        ("Bát ăn chống gù cổ nghiêng 15 độ cho mèo", "Petkit", "Ergonomic Bowl", "猫咪斜口护颈碗 萌宠 好物"),
    ],
    "baby": [
        ("Máy hâm sữa tiệt trùng đa năng Babycare", "Babycare", "Bottle Warmer", "多功能暖奶器 母婴 开箱"),
        ("Xe đẩy em bé gấp gọn du lịch Bebebus", "Bebebus", "Stroller", "便携折叠婴儿车 测评"),
        ("Bình sữa cổ rộng chống sặc Moyuum PPSU 270ml", "Moyuum", "Baby Bottle", "莫辅 奶瓶 防胀气 测评"),
        ("Nồi nấu cháo chậm cách thủy 1L Bear", "Bear", "Slow Cooker 1L", "电炖盅 婴儿辅食 测评 开箱"),
    ],
}


STATE_LABELS = {
    "published": "Đã đăng trên TikTok",
    "ready": "Sẵn sàng đăng (ở mục Đăng bài)",
    "awaiting_approval": "Chờ bạn duyệt (ở mục Đăng bài)",
    "queued": "Đang chờ xử lý",
    "processing": "Đang xử lý / dựng video",
    "search_selected": "Đã chọn, đang chờ tải",
}


def infer_zh_query(title, brand="", model=""):
    t_low = (title or "").casefold()
    if "obagi" in t_low or "bha" in t_low:
        return "欧邦琪 2% 水杨酸 爽肤水 测评 开箱"
    if "torriden" in t_low or "dive in" in t_low:
        return "Torriden 玻尿酸 精华 测评 开箱"
    if "ốp" in t_low or "iphone" in t_low or "case" in t_low:
        return "苹果 手机壳 开箱 测评 好物"
    if "lifebuoy" in t_low or "sữa tắm" in t_low:
        return "沐浴露 测评 种草 好物"
    if "hygiene" in t_low or "xả vải" in t_low:
        return "柔顺剂 开箱 家用 好物"
    if "sweater" in t_low or "áo" in t_low or "quần" in t_low or "bad god" in t_low:
        return "卫衣 套装 穿搭 测评 开箱"
    if "ace68" in t_low or "mchose" in t_low or "bàn phím" in t_low:
        return "迈从 ACE68 磁轴键盘 测评 开箱"
    clean_words = [w for w in (title or "").split() if len(w) >= 3 and not w.startswith("http")]
    return " ".join(clean_words[:3]) + " 测评 开箱"


def infer_product_category(title):
    """Categorize product by name/keywords into one of PRODUCT_CATEGORIES."""
    t = (title or "").casefold()
    if any(
        k in t
        for k in (
            "ốp",
            "điện thoại",
            "iphone",
            "tai nghe",
            "bàn phím",
            "chuột",
            "sạc",
            "loa",
            "đèn",
            "cáp",
            "hub",
            "mic",
            "tản nhiệt",
            "giá đỡ",
            "máy ảnh",
        )
    ):
        return "electronics"
    if any(
        k in t
        for k in (
            "bha",
            "serum",
            "kem",
            "son",
            "phấn",
            "torriden",
            "obagi",
            "nước hoa",
            "rửa mặt",
            "chống nắng",
            "mặt nạ",
            "tinh chất",
            "sấy tóc",
            "mỹ phẩm",
            "dưỡng",
        )
    ):
        return "beauty"
    if any(
        k in t
        for k in ("áo", "quần", "váy", "giày", "dép", "sweater", "hoodie", "balo", "túi", "thắt lưng", "mũ", "nón", "kính", "thời trang")
    ):
        return "fashion"
    if any(
        k in t
        for k in (
            "xả vải",
            "giặt",
            "nước lau",
            "hút bụi",
            "nồi",
            "chảo",
            "bếp",
            "bình giữ nhiệt",
            "robot",
            "lọc không khí",
            "lifebuoy",
            "sữa tắm",
            "gia dụng",
            "nhà cửa",
        )
    ):
        return "home"
    if any(k in t for k in ("trà", "bánh", "kẹo", "hạt", "ngũ cốc", "khô bò", "thực phẩm", "cà phê", "mật ong", "ăn kiêng")):
        return "food"
    if any(k in t for k in ("yoga", "thể thao", "gym", "kháng lực", "con lăn", "shaker", "chạy bộ", "bóng")):
        return "sports"
    if any(k in t for k in ("mèo", "chó", "thú cưng", "pet", "cát vệ sinh", "cho ăn")):
        return "pets"
    if any(k in t for k in ("em bé", "sữa", "tã", "bỉm", "xe đẩy", "ăn dặm", "hâm sữa", "mẹ và bé")):
        return "baby"
    return "electronics"


class VideosMixin:
    def existing_product_videos(self, name_or_model, brand=""):
        """Find if a product/model already exists in store in active states (published, ready, queued, processing)."""
        tokens = set()
        if name_or_model:
            tokens.update(re.findall(r"[A-Za-z0-9]{3,}", name_or_model.casefold()))
        if brand:
            tokens.update(re.findall(r"[A-Za-z0-9]{3,}", brand.casefold()))
        if not tokens:
            return []
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, title, state, account, updated, product_binding FROM jobs "
                "WHERE state IN ('published', 'ready', 'awaiting_approval', 'queued', 'processing', 'search_selected') "
                "ORDER BY updated DESC LIMIT 50"
            ).fetchall()
        matched = []
        for r in rows:
            haystack = (r["title"] or "") + " " + (r["product_binding"] or "")
            hay_lower = haystack.casefold()
            if any(t in hay_lower for t in tokens):
                matched.append(
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "state": r["state"],
                        "state_label": STATE_LABELS.get(r["state"], r["state"]),
                        "account": r["account"],
                    }
                )
        return matched

    def dismissed_products(self, account):
        """Set of product models/names dismissed by the owner."""
        key = "dismissed_products:" + str(account or "default")
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            return set()
        try:
            return set(loads(row["value"], []))
        except Exception:
            return set()

    def dismiss_product(self, account, item_key):
        """Exclude a product from top catalog for this account."""
        if not item_key:
            return
        key = "dismissed_products:" + str(account or "default")
        with self.transaction() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            items = list(loads(row["value"], []) if row else [])
            if item_key not in items:
                items.append(item_key)
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(items)))

    def undismiss_products(self, account):
        """Clear dismissed list to restore all products."""
        key = "dismissed_products:" + str(account or "default")
        with self.transaction() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps([])))

    def category_top_products(self, category, account=None):
        """Top selling products in category, prioritizing confirmed Showcase commission links.
        Never completely hides products that already have videos (allows making new videos for hot products).
        Only excludes explicitly dismissed products."""
        dismissed = {k.casefold() for k in self.dismissed_products(account) if k}
        with self.connect() as db:
            rows = db.execute(
                "SELECT title, product_binding FROM jobs "
                "WHERE state IN ('published', 'ready', 'awaiting_approval', 'queued', 'processing', 'search_selected')"
            ).fetchall()
        existing_tokens = [(r["title"] or "") + " " + (r["product_binding"] or "") for r in rows]

        def count_existing(key):
            if not key or len(key) < 3:
                return 0
            k_low = key.casefold()
            return sum(1 for t in existing_tokens if k_low in t.casefold())

        available = []

        # 1. Prioritize account's confirmed Showcase products matching this category
        if account:
            account_links = self.commission_list(account)
            for l in account_links:
                l_title = l.get("title") or ""
                l_pid = str(l.get("product_id") or "")
                check_key = l_pid.casefold() if l_pid else l_title.casefold()
                if check_key in dismissed or l_title.casefold() in dismissed:
                    continue
                prod_cat = infer_product_category(l_title)
                if prod_cat != category:
                    continue
                c_cnt = count_existing(l_pid) or count_existing(l_title)
                available.append(
                    {
                        "name": l_title,
                        "brand": "Showcase",
                        "model": l_pid,
                        "product_id": l_pid,
                        "url": l.get("url") or "",
                        "query_zh": infer_zh_query(l_title, model=l_pid),
                        "existing_count": c_cnt,
                        "is_showcase": True,
                    }
                )

        # 2. General catalog items for this category
        catalog = TOP_SALES_CATALOG.get(category, [])
        for item in catalog:
            name, brand, model, zh_query = item
            check_key = model.casefold() if model else name.casefold()
            if check_key in dismissed or name.casefold() in dismissed or (brand and brand.casefold() in dismissed):
                continue
            if any(a["name"].casefold() == name.casefold() for a in available):
                continue
            c_cnt = count_existing(model) or count_existing(name)
            available.append(
                {
                    "name": name,
                    "brand": brand,
                    "model": model,
                    "product_id": model,
                    "url": "",
                    "query_zh": zh_query,
                    "existing_count": c_cnt,
                    "is_showcase": False,
                }
            )

        # Sort: items with 0 existing videos first, then items with existing videos
        available.sort(key=lambda x: (x.get("existing_count", 0), not x.get("is_showcase", False)))
        return available

    def videos_new(self, items):
        """Filter a new answer against every existing job without touching selected answers or job state."""
        items = items[:40]
        if not items:
            return [], 0
        keys = [(i.get("platform", "tiktok"), i["source_id"]) for i in items]
        urls = [i["url"] for i in items]
        key_slots = ",".join("(?,?)" for _ in keys)
        url_slots = ",".join("?" for _ in urls)
        with self.connect() as db:
            rows = db.execute(
                "SELECT platform,source_id,url FROM jobs WHERE (platform,source_id) IN (%s) OR url IN (%s)" % (key_slots, url_slots),
                [value for pair in keys for value in pair] + urls,
            ).fetchall()
        known = {(row[0], row[1]) for row in rows}
        known_urls = {row[2] for row in rows}
        new = [i for i in items if (i.get("platform", "tiktok"), i["source_id"]) not in known and i["url"] not in known_urls]
        return new, len(items) - len(new)

    def videos_rank(self, mid, items, limit=MAX_RESULTS, identity=None):
        """The candidates an agent reported, as the chat shows them: each judged against the product, best first, different products last."""
        body = self.chat_get(mid)["body"]
        identity = identity if identity is not None else body.get("identity", {})
        out, seen = [], set()
        for item in items[:40]:
            source_id = item.get("source_id")
            if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source_id):
                continue
            key = (item.get("platform", "tiktok"), source_id)
            if key in seen:
                continue
            candidate = {k: item.get(k) for k in ("source_id", "title", "platform", "media", "duration", "product_id")}
            try:
                candidate["url"] = canonical_url(item.get("platform", "tiktok"), item.get("url", ""))
            except (ValueError, KeyError, AttributeError, TypeError):
                continue  # one video the agent described badly is left out, not a reason to lose the others
            candidate["match"] = match_identity(identity, item.get("title", ""))  # source video IDs are not Shop product identities
            for metric in ("views", "likes"):
                value = item.get(metric)
                candidate[metric] = value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10**12 else None
            seen.add(key)
            out.append(candidate)
        sales = bool((body.get("discovery") or {}).get("sales", False))
        if sales:
            # Exclude old, damaged, repair or scrap items when searching for sales videos
            out = [i for i in out if not (i.get("match") or {}).get("is_old")]

            def sales_key(i):
                match = i.get("match") or {}
                is_diff = match.get("level") == "different"
                is_comm = match.get("commercial", False)
                score = match.get("score", 0)
                comm_score = match.get("commercial_score", 0)
                # Tier: 2 for product matched + commercial intent, 1 for matched only, 0 for different products
                tier = 0 if is_diff else (2 if is_comm else 1)
                combined = score + (comm_score if is_comm else 0)
                return (tier, combined, i.get("views") or 0, i.get("likes") or 0)

            return sorted(out, key=sales_key, reverse=True)[:limit]
        return sorted(out, key=lambda i: (i["match"]["score"], i.get("views") or 0, i.get("likes") or 0), reverse=True)[:limit]

    def videos_dismiss(self, mid, platform, source_id):
        """Do not remove the source information while a selected video's download still needs it."""
        with self.transaction() as db:
            row = db.execute("SELECT kind,state,body FROM chat WHERE id=?", (mid,)).fetchone()
            if not row or row["kind"] != "videos" or row["state"] != "done":
                raise ValueError("Lượt tìm chưa hoàn tất")
            if db.execute(
                "SELECT 1 FROM jobs WHERE search_id=? AND platform=? AND source_id=?", (str(mid), platform, source_id)
            ).fetchone():
                raise ValueError("Video đã được chọn; dùng Bỏ chờ trong hàng đợi")
            body = json.loads(row["body"])
            items = body.get("results", [])
            remaining = [i for i in items if (i.get("platform"), i.get("source_id")) != (platform, source_id)]
            if len(remaining) == len(items):
                raise ValueError("Không có ứng viên này")
            item = next(i for i in items if (i.get("platform"), i.get("source_id")) == (platform, source_id))
            url = canonical_url(platform, item["url"])
            if not db.execute("SELECT 1 FROM jobs WHERE (platform=? AND source_id=?) OR url=?", (platform, source_id, url)).fetchone():
                now = time.time()
                db.execute(
                    "INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,last_seen,state,reason,updated) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        uuid.uuid4().hex,
                        platform,
                        source_id,
                        url,
                        COUNTRIES[platform],
                        item.get("title") or "Video đã bỏ",
                        now,
                        now,
                        "rejected",
                        "Bạn đã bỏ ứng viên tìm kiếm; không lấy lại",
                        now,
                    ),
                )
            body["results"] = remaining
            db.execute("UPDATE chat SET body=? WHERE id=?", (json.dumps(body, ensure_ascii=False), mid))
        return {"id": mid}

    def _videos_message(self, mid):
        message = self.chat_get(mid)
        if message["kind"] != "videos" or message["state"] != "done":
            raise ValueError("Cần chọn video và xác nhận đã xem đúng sản phẩm")
        if (self.account(message["account"]) or {}).get("username") != message["body"].get("account_username"):
            raise ValueError("Tài khoản đã thay đổi từ lúc tìm kiếm; hãy tìm lại")
        return message

    def videos_select(self, mid, source_id, confirmed=False, platform=None):
        """Idempotent and pinned to its account. A video already used by another search or account is never reassigned or posted twice."""
        if not confirmed:
            raise ValueError("Cần chọn video và xác nhận đã xem đúng sản phẩm")
        message = self._videos_message(mid)
        body = message["body"]
        matches = [
            i
            for i in body.get("results", [])
            if i["source_id"] == source_id and (platform is None or i.get("platform", "tiktok") == platform)
        ]
        if len(matches) != 1:
            raise ValueError("Cần chọn đúng nguồn và video trong kết quả")
        item = matches[0]
        if candidate_match(body.get("identity", {}), item)["level"] == "different":
            raise ValueError("Video thuộc sản phẩm khác; không thể chọn")
        sid = str(mid)
        with self.transaction() as db:
            fresh = db.execute("SELECT body,state FROM chat WHERE id=?", (mid,)).fetchone()
            account = db.execute("SELECT username FROM accounts WHERE id=?", (message["account"],)).fetchone()
            if not fresh or fresh["state"] != "done" or json.loads(fresh["body"]) != body:
                raise ValueError("Kết quả vừa thay đổi; hãy tải lại trước khi chọn")
            if not account or account[0] != body.get("account_username"):
                raise ValueError("Tài khoản đã thay đổi; hãy tìm lại")
            row = db.execute("SELECT id,search_id FROM jobs WHERE url=?", (item["url"],)).fetchone()
            if row:
                if row["search_id"] != sid:
                    raise ValueError("Video đã có trong hệ thống; không chuyển sang tài khoản khác hoặc đăng trùng")
                return row["id"]
            jid, now = uuid.uuid4().hex, time.time()
            platform = item.get("platform") or "tiktok"
            if db.execute("SELECT 1 FROM jobs WHERE platform=? AND source_id=?", (platform, source_id)).fetchone():
                raise ValueError("Video đã có trong hệ thống (cùng mã, có thể khác tên kênh); không chọn lại")

            identity = body.get("identity", {})
            links = [
                dict(r)
                for r in db.execute("SELECT account,url,title,product_id FROM commission_links WHERE account=?", (message["account"],))
            ]
            affiliate_binding = catalog_binding(identity, links, message["account"], body["account_username"])
            is_sales = bool((body.get("discovery") or {}).get("sales") or identity.get("sales"))
            if is_sales and not affiliate_binding:
                raise ValueError("Chưa có sản phẩm Shop duy nhất đúng hãng/model/biến thể trong tài khoản; chưa thể tạo giỏ hàng")

            meta = {
                "product_reference": body.get("identity", {}),
                "search_username": body.get("account_username"),
                "product_binding": affiliate_binding,
                "commerce_required": is_sales,
            }
            binding_str = json.dumps(affiliate_binding) if affiliate_binding else None
            db.execute(
                "INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,last_seen,state,reason,updated,meta,search_id,search_account,product_binding) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid, platform, source_id, item["url"], COUNTRIES[platform], item.get("title") or "Video đã chọn", now, now,
                    "search_selected", "Bạn đã chọn; đang chờ tải", now, json.dumps(meta), sid, message["account"], binding_str,
                ),
            )  # fmt: skip
        return jid

    def videos_media_ready(self, jid):
        """Claim a picked video for downloading: {'id','item','account'}. Only a video still waiting to be downloaded can be claimed. A pick
        whose answer is gone (older than the log keeps) or whose account changed can never be downloaded: it is rejected, not left waiting.
        """
        stale = False
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND state='search_selected'", (jid,)).fetchone()
            if not row:
                raise ValueError("Video đã được tải hoặc không còn chờ tải")
            try:
                message = self._videos_message(int(row["search_id"]))
                item = next(
                    i
                    for i in message["body"]["results"]
                    if i["source_id"] == row["source_id"] and i.get("platform", "tiktok") == row["platform"]
                )
            except (ValueError, StopIteration, KeyError):
                stale = True
                db.execute(
                    "UPDATE jobs SET state='rejected',reason=?,updated=? WHERE id=?",
                    ("Lượt chọn không còn dùng được (tin nhắn đã cũ hoặc tài khoản đã đổi); hãy tìm và chọn lại", time.time(), jid),
                )
            else:
                db.execute("UPDATE jobs SET state='candidate',updated=? WHERE id=?", (time.time(), jid))
        if stale:  # raised after the transaction closes, or the rejection would be rolled back with it
            raise ValueError("Lượt chọn này không còn dùng được; hãy tìm và chọn lại")
        return {"id": jid, "item": item, "account": row["search_account"]}

    def video_download_failed(self, jid, reason):
        """A download that failed puts the pick back to 'waiting', with the reason, so the owner can pick it again."""
        with self.transaction() as db:
            db.execute(
                "UPDATE jobs SET state='search_selected',reason=? WHERE id=? AND state='candidate' AND source_file IS NULL",
                (reason[:700], jid),
            )
