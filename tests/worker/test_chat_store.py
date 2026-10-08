"""The chat log, picking a video out of an answer, and the commission links the owner confirmed."""

import json
import time

from tests.support import StoreCase


def result(source_id="1234567890", platform="tiktok", url=None, level="candidate"):
    return {
        "source_id": source_id, "platform": platform, "title": "Samsung S24", "media": {"kind": "direct"},
        "url": url or "https://www.tiktok.com/@a/video/" + source_id, "match": {"level": level, "score": 100, "reason": "keywords"},
    }  # fmt: skip


class ChatLogTests(StoreCase):
    def test_a_message_keeps_its_body_and_the_thread_reads_oldest_first(self):
        first = self.s.chat_add("user", "say", {"text": "Samsung S24"}, account="main")
        second = self.s.chat_add("bot", "product", {"identity": {"name": "Samsung S24"}}, state="running")
        thread = self.s.chat_thread()
        self.assertEqual([m["id"] for m in thread], [first, second])
        self.assertEqual((thread[0]["role"], thread[0]["account"], thread[0]["body"]), ("user", "main", {"text": "Samsung S24"}))
        self.assertEqual(thread[1]["state"], "running")

    def test_set_changes_the_state_and_merges_fields_without_losing_the_rest(self):
        mid = self.s.chat_add("bot", "videos", {"identity": {"name": "S24"}, "note": "x"}, state="running")
        self.s.chat_set(mid, "done", results=[1])
        message = self.s.chat_get(mid)
        self.assertEqual((message["state"], message["body"]), ("done", {"identity": {"name": "S24"}, "note": "x", "results": [1]}))
        self.s.chat_set(mid, note="y")
        self.assertEqual((self.s.chat_get(mid)["state"], self.s.chat_get(mid)["body"]["note"]), ("done", "y"))

    def test_unknown_roles_kinds_states_and_messages_are_refused(self):
        for args in (("owner", "say", {}), ("user", "poem", {}), ("user", "say", {}, "stuck")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.s.chat_add(*args)
        with self.assertRaises(ValueError):
            self.s.chat_get(999)
        with self.assertRaises(ValueError):
            self.s.chat_set(999, "done")

    def test_the_product_in_question_is_the_latest_finished_product_answer(self):
        self.assertIsNone(self.s.chat_product())
        self.s.chat_add("bot", "product", {"identity": {"name": "old"}})
        newest = self.s.chat_add("bot", "product", {"identity": {"name": "new"}})
        self.s.chat_add("bot", "product", {"identity": {"name": "unfinished"}}, state="running")
        self.s.chat_add("bot", "videos", {})
        self.assertEqual(self.s.chat_product()["id"], newest)

    def test_only_a_few_answers_may_be_unfinished_at_once(self):
        for _ in range(3):
            self.s.chat_add("bot", "videos", {}, state="running")
        with self.assertRaises(ValueError):
            self.s.chat_add("bot", "videos", {}, state="pending")
        self.s.chat_add("bot", "note", {"text": "finished messages are not limited"})

    def test_a_message_and_its_answer_are_kept_together_or_not_at_all(self):
        mid = self.s.chat_ask("main", {"text": "S24"}, "product", {})
        thread = self.s.chat_thread()
        self.assertEqual([(m["role"], m["kind"], m["state"]) for m in thread], [("user", "say", "done"), ("bot", "product", "running")])
        self.assertEqual(thread[1]["id"], mid)
        for _ in range(2):
            self.s.chat_ask("main", {"text": "more"}, "product", {})
        with self.assertRaises(ValueError):
            self.s.chat_ask("main", {"text": "one too many"}, "product", {})
        self.assertNotIn("one too many", [m["body"].get("text") for m in self.s.chat_thread()])

    def test_old_messages_are_dropped_beyond_the_limit(self):
        from trendvn_worker.store import chat

        ids = [self.s.chat_add("user", "say", {"text": str(i)}) for i in range(chat.KEEP + 5)]
        thread = self.s.chat_thread(limit=1000)
        self.assertEqual(len(thread), chat.KEEP)
        self.assertEqual(thread[0]["id"], ids[5])

    def test_a_damaged_body_does_not_stop_the_restart_cleanup(self):
        mid = self.s.chat_add("bot", "videos", {}, state="running")
        with self.s.transaction() as db:
            db.execute("UPDATE chat SET body='not json{' WHERE id=?", (mid,))
        self.s.chat_recover()
        self.assertEqual(self.s.chat_get(mid)["state"], "error")

    def test_after_a_restart_unfinished_answers_become_errors_and_downloads_wait_to_be_picked_again(self):
        mid = self.s.chat_add("bot", "videos", {"results": []}, state="running")
        done = self.s.chat_add("bot", "note", {"text": "ok"})
        self.job("a1", "candidate", search_id=str(mid), search_account="main", source_file=None)
        self.s.chat_recover()
        self.assertEqual(self.s.chat_get(mid)["state"], "error")
        self.assertIn("gián đoạn", self.s.chat_get(mid)["body"]["error"])
        self.assertEqual(self.s.chat_get(done)["state"], "done")
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='a1'").fetchone()[0], "search_selected")


class VideoPickTests(StoreCase):
    def answer(self, results=None, account="main"):
        name = (self.s.account(account) or {}).get("username")
        body = {"identity": {"name": "Samsung S24"}, "account_username": name, "results": results if results is not None else [result()]}
        return self.s.chat_add("bot", "videos", body, state="done", account=account)

    def test_the_pick_needs_the_owners_confirmation_and_is_idempotent(self):
        mid = self.answer()
        with self.assertRaises(ValueError):
            self.s.videos_select(mid, "1234567890")
        jid = self.s.videos_select(mid, "1234567890", True)
        self.assertEqual(jid, self.s.videos_select(mid, "1234567890", True))
        with self.s.connect() as db:
            row = db.execute("SELECT state,search_id,search_account,country FROM jobs WHERE id=?", (jid,)).fetchone()
        self.assertEqual(tuple(row), ("search_selected", str(mid), "main", "US"))

    def test_a_video_already_picked_by_another_answer_is_not_taken_again(self):
        self.s.videos_select(self.answer(), "1234567890", True)
        with self.assertRaises(ValueError):
            self.s.videos_select(self.answer(), "1234567890", True)

    def test_a_video_the_system_already_has_under_another_channel_name_is_a_clean_refusal_not_a_crash(self):
        self.job("7000000001", "queued", platform="tiktok", url="https://www.tiktok.com/@oldname/video/7000000001")
        mid = self.answer([result("7000000001", url="https://www.tiktok.com/@newname/video/7000000001")])
        with self.assertRaises(ValueError) as caught:
            self.s.videos_select(mid, "7000000001", True)
        self.assertIn("đã có trong hệ thống", str(caught.exception))

    def test_a_pick_whose_answer_was_pruned_or_whose_account_changed_is_rejected_not_left_waiting_forever(self):
        mid = self.answer()
        jid = self.s.videos_select(mid, "1234567890", True)
        with self.s.transaction() as db:
            db.execute("DELETE FROM chat WHERE id=?", (mid,))
        with self.assertRaises(ValueError):
            self.s.videos_media_ready(jid)
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()[0], "rejected")

    def test_a_pick_nobody_downloaded_for_days_expires_like_any_candidate(self):
        from trendvn_worker.store import retention

        jid = self.s.videos_select(self.answer(), "1234567890", True)
        self.s.prune(now=time.time() + (retention.CANDIDATE_EXPIRY_DAYS + 1) * 86400)
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()[0], "rejected")

    def test_a_video_of_another_product_cannot_be_picked(self):
        mid = self.answer([result(level="different")])
        with self.assertRaises(ValueError):
            self.s.videos_select(mid, "1234567890", True)

    def test_a_stored_match_is_rechecked_before_pick_under_current_model_rules(self):
        mid = self.answer([result() | {"title": "Samsung S25 compared with S24"}])
        with self.assertRaisesRegex(ValueError, "sản phẩm khác"):
            self.s.videos_select(mid, "1234567890", True)

    def test_dismissed_search_video_is_never_offered_again_after_history_clear(self):
        mid = self.answer()
        self.s.videos_dismiss(mid, "tiktok", "1234567890")
        self.s.chat_clear()
        self.assertEqual(self.s.videos_new([result()]), ([], 1))
        with self.s.connect() as db:
            row = db.execute("SELECT state,search_id,search_account,source_file FROM jobs").fetchone()
        self.assertEqual(tuple(row), ("rejected", None, None, None))

    def test_dismiss_keeps_an_existing_job_from_another_search_unchanged(self):
        picked = self.s.videos_select(self.answer(), "1234567890", True)
        with self.s.connect() as db:
            before = dict(db.execute("SELECT * FROM jobs WHERE id=?", (picked,)).fetchone())
        self.s.videos_dismiss(self.answer(), "tiktok", "1234567890")
        with self.s.connect() as db:
            after = dict(db.execute("SELECT * FROM jobs WHERE id=?", (picked,)).fetchone())
        self.assertEqual(before, after)

    def test_select_and_dismiss_in_other_answers_cannot_duplicate_or_replace_a_job(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        for number in range(5):
            sid = str(7000000000 + number)
            pick_mid, dismiss_mid = self.answer([result(sid)]), self.answer([result(sid)])
            ready = Barrier(2)

            def run(pick):
                ready.wait(timeout=3)
                try:
                    if pick:
                        return self.s.videos_select(pick_mid, sid, True)
                    return self.s.videos_dismiss(dismiss_mid, "tiktok", sid)
                except ValueError:
                    return None

            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(run, (True, False)))
            with self.s.connect() as db:
                rows = db.execute("SELECT state,search_id FROM jobs WHERE source_id=?", (sid,)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertIn(tuple(rows[0]), (("rejected", None), ("search_selected", str(pick_mid))))

    def test_an_unfinished_or_foreign_message_cannot_be_picked_from(self):
        name = self.s.account("main")["username"]
        running = self.s.chat_add("bot", "videos", {"results": [result()], "account_username": name}, state="running", account="main")
        said = self.s.chat_add("user", "say", {"results": [result()], "account_username": name}, account="main")
        for mid in (running, said):
            with self.assertRaises(ValueError):
                self.s.videos_select(mid, "1234567890", True)

    def test_the_pick_does_not_follow_a_changed_account(self):
        mid = self.answer()
        jid = self.s.videos_select(mid, "1234567890", True)
        with self.s.transaction() as db:
            db.execute("UPDATE accounts SET username='replacement' WHERE id='main'")
            db.execute("UPDATE jobs SET state='ready',output_file='/d/a.mp4' WHERE id=?", (jid,))
        with self.assertRaises(ValueError):
            self.s.videos_select(mid, "1234567890", True)
        with self.assertRaises(ValueError):
            self.s.publish_peek(jid)

    def test_download_is_claimed_once_and_kept_from_the_regular_collector(self):
        jid = self.s.videos_select(self.answer(), "1234567890", True)
        claimed = self.s.videos_media_ready(jid)
        self.assertEqual((claimed["account"], claimed["item"]["source_id"]), ("main", "1234567890"))
        self.assertEqual(self.s.candidates_without_media(), [])
        with self.assertRaises(ValueError):
            self.s.videos_media_ready(jid)

    def test_the_same_id_on_two_sources_needs_the_platform_and_gets_the_right_country(self):
        items = [
            result(platform="douyin", url="https://www.douyin.com/video/1234567890"),
            result(platform="tiktok"),
        ]
        mid = self.answer(items)
        with self.assertRaises(ValueError):
            self.s.videos_select(mid, "1234567890", True)
        jid = self.s.videos_select(mid, "1234567890", True, "douyin")
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT country FROM jobs WHERE id=?", (jid,)).fetchone()[0], "CN")
        self.assertEqual(self.s.videos_media_ready(jid)["item"]["platform"], "douyin")

    def test_a_regular_collection_cannot_move_a_picked_video_to_another_account(self):
        jid = self.s.videos_select(self.answer(), "1234567890", True)
        report = {
            "platform": "tiktok", "stream": "test", "observed_at": 100,
            "items": [{
                "source_id": "1234567890", "url": "https://www.tiktok.com/@a/video/1234567890", "country": "US", "title": "Samsung S24",
                "rank": 1, "views": 1000, "evidence_url": "https://www.tiktok.com/search?q=S24", "meta": {"score": 900},
            }],
        }  # fmt: skip
        self.s.ingest(report, now=100)
        with self.s.connect() as db:
            meta = json.loads(db.execute("SELECT meta FROM jobs WHERE id=?", (jid,)).fetchone()[0])
        self.assertEqual(meta["search_username"], self.s.account("main")["username"])


class RankTests(StoreCase):
    def test_one_video_the_agent_described_badly_is_left_out_not_a_reason_to_lose_the_others(self):
        mid = self.s.chat_add("bot", "videos", {"identity": {"name": "S24", "model": "S24"}}, state="running", account="main")
        good = {"source_id": "1111111111", "platform": "tiktok", "url": "https://www.tiktok.com/@a/video/1111111111", "title": "S24"}
        for bad in ({"url": "javascript:alert(1)"}, {"url": None}, {"platform": "myspace"}, {"url": "https://evil.example/x"}):
            ranked = self.s.videos_rank(mid, [good | {"source_id": "2222222222"} | bad, good])
            self.assertEqual([r["source_id"] for r in ranked], ["1111111111"], bad)

    def test_candidates_are_ordered_by_match_with_other_products_last_and_bad_ids_dropped(self):
        mid = self.s.chat_add(
            "bot", "videos", {"identity": {"name": "Samsung Galaxy S24", "model": "S24"}}, state="running", account="main"
        )
        items = [
            {
                "source_id": "2222222222",
                "platform": "tiktok",
                "url": "https://www.tiktok.com/@a/video/2222222222",
                "title": "Samsung Galaxy S23",
            },
            {
                "source_id": "1111111111",
                "platform": "tiktok",
                "url": "https://www.tiktok.com/@a/video/1111111111",
                "title": "Samsung Galaxy S24 review",
            },
            {"source_id": "../x", "platform": "tiktok", "url": "https://www.tiktok.com/@a/video/3333333333", "title": "Samsung Galaxy S24"},
        ]
        ranked = self.s.videos_rank(mid, items)
        self.assertEqual([r["source_id"] for r in ranked], ["1111111111", "2222222222"])
        self.assertEqual(ranked[1]["match"]["level"], "different")


class CommissionTests(StoreCase):
    FOUND = {
        "input": "https://vt.tiktok.com/ZSabc/",
        "product_id": "1729384756102938475",
        "title": "Bàn phím",
        "markers": {"share_creator_id": "7"},
        "tracked": True,
    }

    def test_a_confirmed_link_is_kept_per_account_and_product_and_its_marks_become_the_reference(self):
        self.assertEqual(self.s.commission_known("main"), [])
        self.s.commission_save("main", self.FOUND)
        self.assertEqual(self.s.commission_known("main"), [{"share_creator_id": "7"}])
        saved = self.s.commission_get("main", self.FOUND["product_id"])
        self.assertEqual((saved["url"], saved["title"]), (self.FOUND["input"], "Bàn phím"))
        self.assertIsNone(self.s.commission_get("main", "999999"))

    def test_a_second_confirmation_for_the_same_product_replaces_the_first(self):
        self.s.commission_save("main", self.FOUND)
        self.s.commission_save("main", dict(self.FOUND, input="https://vt.tiktok.com/ZSnew/"))
        self.assertEqual(self.s.commission_get("main", self.FOUND["product_id"])["url"], "https://vt.tiktok.com/ZSnew/")
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM commission_links").fetchone()[0], 1)

    def test_a_plain_link_confirmed_by_the_owner_teaches_no_marks(self):
        self.s.commission_save("main", dict(self.FOUND, markers={}, tracked=False))
        self.assertEqual(self.s.commission_known("main"), [])

    def test_a_link_needs_an_existing_account_and_a_product(self):
        for account, found in (("nobody", self.FOUND), ("main", dict(self.FOUND, product_id=None))):
            with self.assertRaises(ValueError):
                self.s.commission_save(account, found)


class MigrationTests(StoreCase):
    def test_a_database_that_ran_the_first_version_of_migration_6_gets_the_chat_tables(self):
        """Commits before this one shipped a different migration 6 (a `searches` table): such a database is at version 6 without a chat."""
        from trendvn_worker.store import Store, schema

        with self.s.transaction() as db:
            db.execute("DROP TABLE chat")
            db.execute("DROP TABLE commission_links")
            db.execute("CREATE TABLE searches (id TEXT PRIMARY KEY, account TEXT NOT NULL)")
            db.execute("INSERT INTO searches VALUES('old','main')")
            db.execute("PRAGMA user_version = 6")
        reopened = Store(self.tmp.name)
        self.assertEqual(reopened.chat_thread(), [])
        reopened.chat_add("user", "say", {"text": "ok"})
        with reopened.connect() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], len(schema.MIGRATIONS))
            self.assertEqual(db.execute("SELECT id FROM searches").fetchall()[0][0], "old")  # nothing of the owner's is dropped
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")


class ChannelTests(StoreCase):
    def test_what_is_known_of_each_sign_in_is_kept_per_account_and_channel_and_the_latest_report_wins(self):
        self.assertEqual(self.s.channel_states(), {})
        self.s.channel_report("main", "douyin", "wall")
        self.s.channel_report("main", "tiktok", "ok", who="creator")
        self.s.channel_report("main", "douyin", "ok", who="")
        states = self.s.channel_states()["main"]
        self.assertEqual((states["douyin"]["state"], states["tiktok"]["state"], states["tiktok"]["who"]), ("ok", "ok", "creator"))
        self.assertGreater(states["douyin"]["at"], 0)

    def test_an_unknown_account_channel_or_state_is_refused(self):
        for args in (("nobody", "douyin", "ok"), ("main", "myspace", "ok"), ("main", "douyin", "maybe")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.s.channel_report(*args)

    def test_a_deleted_account_takes_its_sign_in_records_and_saved_links_with_it(self):
        other = self.s.add_account({"username": "other_shop", "topics": ["food"]})["id"]
        self.s.channel_report(other, "douyin", "ok")
        self.s.channel_report("main", "douyin", "ok")
        self.s.commission_save(other, CommissionTests.FOUND)
        self.s.delete_account(other)
        self.assertEqual(list(self.s.channel_states()), ["main"])
        self.assertEqual(self.s.commission_list(other), [])


class ClearHistoryTests(StoreCase):
    def test_clearing_removes_finished_messages_but_not_work_in_progress_or_picks_waiting_for_download(self):
        old = self.s.chat_add("user", "say", {"text": "old"}, account="main")
        product = self.s.chat_add("bot", "product", {"identity": {"name": "S24"}}, account="main")
        running = self.s.chat_add("bot", "videos", {}, state="running", account="main")
        name = self.s.account("main")["username"]
        picked = self.s.chat_add("bot", "videos", {"identity": {}, "account_username": name, "results": [result()]}, account="main")
        jid = self.s.videos_select(picked, "1234567890", True)
        removed = self.s.chat_clear()
        self.assertEqual(removed, 3)
        left = {m["id"] for m in self.s.chat_thread()}
        self.assertEqual(left, {running})
        self.assertNotIn(old, left)
        self.assertNotIn(product, left)
        self.assertEqual(self.s.videos_media_ready(jid)["account"], "main")  # the pick can still be downloaded

    def test_once_the_pick_is_downloaded_its_answer_can_be_cleared_and_the_video_stays_in_the_system(self):
        name = self.s.account("main")["username"]
        picked = self.s.chat_add("bot", "videos", {"identity": {}, "account_username": name, "results": [result()]}, account="main")
        jid = self.s.videos_select(picked, "1234567890", True)
        self.s.videos_media_ready(jid)
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET state='queued' WHERE id=?", (jid,))
        self.assertEqual(self.s.chat_clear(), 1)
        self.assertEqual(self.s.chat_thread(), [])
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()[0], "queued")

    def test_clearing_never_touches_saved_links_or_sign_in_records(self):
        self.s.commission_save("main", CommissionTests.FOUND)
        self.s.channel_report("main", "douyin", "ok")
        self.s.chat_add("user", "say", {"text": "x"}, account="main")
        self.s.chat_clear()
        self.assertIsNotNone(self.s.commission_get("main", CommissionTests.FOUND["product_id"]))
        self.assertEqual(self.s.channel_states()["main"]["douyin"]["state"], "ok")

    def test_only_what_is_older_than_the_cutoff_goes_when_one_is_given(self):
        old = self.s.chat_add("user", "say", {"text": "old"})
        recent = self.s.chat_add("user", "say", {"text": "recent"})
        with self.s.transaction() as db:
            db.execute("UPDATE chat SET created=? WHERE id=?", (time.time() - 40 * 86400, old))
        self.assertEqual(self.s.chat_clear(before=time.time() - 30 * 86400), 1)
        self.assertEqual([m["id"] for m in self.s.chat_thread()], [recent])

    def test_housekeeping_forgets_search_history_older_than_a_month_and_nothing_else(self):
        from trendvn_worker.store import retention

        old = self.s.chat_add("user", "say", {"text": "old"})
        running = self.s.chat_add("bot", "videos", {}, state="running")
        recent = self.s.chat_add("user", "say", {"text": "recent"})
        self.s.commission_save("main", CommissionTests.FOUND)
        with self.s.transaction() as db:
            db.execute("UPDATE chat SET created=? WHERE id IN (?,?)", (time.time() - (retention.KEEP_CHAT_DAYS + 1) * 86400, old, running))
        result = self.s.prune()
        self.assertGreaterEqual(result["rows_trimmed"], 1)
        self.assertEqual({m["id"] for m in self.s.chat_thread()}, {running, recent})
        self.assertIsNotNone(self.s.commission_get("main", CommissionTests.FOUND["product_id"]))

    def test_the_product_a_running_search_was_started_for_is_kept_so_its_retry_still_works(self):
        product = self.s.chat_add("bot", "product", {"identity": {"name": "S24"}}, account="main")
        other = self.s.chat_add("bot", "product", {"identity": {"name": "other"}}, account="main")
        running = self.s.chat_add("bot", "videos", {"product": product}, state="running", account="main")
        self.assertEqual(self.s.chat_clear(), 2)
        self.assertEqual({m["id"] for m in self.s.chat_thread()}, {running})
        self.assertEqual(self.s.chat_get(product)["body"]["identity"]["name"], "S24")
        self.assertNotIn(other, {m["id"] for m in self.s.chat_thread()})

    def test_clearing_an_empty_history_is_fine(self):
        self.assertEqual(self.s.chat_clear(), 0)


class TikTokSignInIsOneFactTests(StoreCase):
    """The Accounts tab's 'đã đăng nhập TikTok' and the search channel's TikTok row are the same fact, whichever side learns it."""

    def accounts_view(self):
        return {a["id"]: a["logged_in"] for a in self.s.status()["accounts"]}

    def test_what_the_search_channel_learns_reaches_the_accounts_tab(self):
        self.s.channel_report("main", "tiktok", "out")
        self.assertIs(self.accounts_view()["main"], False)
        self.s.channel_report("main", "tiktok", "ok", who="creator")
        self.assertIs(self.accounts_view()["main"], True)

    def test_what_the_publisher_learns_reaches_the_search_channel(self):
        self.s.set_account_login("main", True)
        self.assertEqual(self.s.channel_states()["main"]["tiktok"]["state"], "ok")
        self.s.set_account_login("main", False)
        self.assertEqual(self.s.channel_states()["main"]["tiktok"]["state"], "out")

    def test_a_verification_wall_on_tiktok_is_not_a_signed_out_account_and_douyin_never_touches_the_accounts_tab(self):
        self.s.set_account_login("main", True)
        self.s.channel_report("main", "tiktok", "wall")
        self.assertIs(self.accounts_view()["main"], True)
        self.s.channel_report("main", "douyin", "out")
        self.assertIs(self.accounts_view()["main"], True)

    def test_the_schedules_repeated_report_of_the_same_state_does_not_rewrite_the_record(self):
        self.s.set_account_login("main", True)
        first = self.s.channel_states()["main"]["tiktok"]["at"]
        self.s.set_account_login("main", True)
        self.assertEqual(self.s.channel_states()["main"]["tiktok"]["at"], first)


class SavedLinkListTests(StoreCase):
    def test_saved_links_are_listed_newest_first_per_account_and_can_be_forgotten_one_by_one(self):
        found = CommissionTests.FOUND
        self.s.commission_save("main", found)
        self.s.commission_save(
            "main", dict(found, product_id="1729384756102938999", input="https://vt.tiktok.com/ZSsecond/", title="Second")
        )
        listed = self.s.commission_list("main")
        self.assertEqual([item["title"] for item in listed], ["Second", "Bàn phím"])
        self.assertEqual(self.s.commission_list("nobody"), [])
        self.assertTrue(self.s.commission_forget("main", found["product_id"]))
        self.assertFalse(self.s.commission_forget("main", found["product_id"]))
        self.assertEqual([item["title"] for item in self.s.commission_list("main")], ["Second"])
