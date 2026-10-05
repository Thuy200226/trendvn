"""Google Gemini HTTP client: local daily budget, model fallback chain, overload handling."""

import json
import re
import time
import urllib.error
import urllib.request

from ..domain.settings import MODEL_FALLBACKS
from .errors import KeyRejected, RateLimited, Transient

TRANSIENT = (429, 500, 502, 503, 504)
BASE = "https://generativelanguage.googleapis.com/v1beta/"
DAILY_QUOTA = "daily quota"  # marker `gemini()` puts in a 429 message when Google's details name a per-day limit (the text is the same for a per-minute one)


def gemini(store, model, body, endpoint=None):
    """One call to the Gemini API with the local daily budget. `endpoint` is the path after /v1beta/ when it is not the model's
    generateContent (the current TTS models speak the Interactions API: endpoint "interactions", the model named in the body)."""
    key_file = store.root / "gemini.key"
    if not key_file.exists():
        raise ValueError("Gemini API key is not configured")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", model):
        raise ValueError("Invalid Gemini model")
    with store.transaction() as db:
        used = db.execute("SELECT count(*) FROM api_calls WHERE at>?", (time.time() - 86400,)).fetchone()[0]
        limit = store.settings().get("gemini_daily_limit", 12)
        if used >= limit:
            raise RateLimited("Local rolling 24-hour limit of %d Gemini calls reached" % limit)
        stamp = time.time()
        db.execute("INSERT INTO api_calls VALUES(?,?,?)", (stamp, model, "started"))
    request = urllib.request.Request(
        BASE + (endpoint or "models/" + model + ":generateContent"),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key_file.read_text().strip()},
    )
    try:
        with urllib.request.urlopen(request, timeout=100) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 403, 404) + TRANSIENT:
            with store.transaction() as db:  # a rejected request was not processed, so it does not use up the daily allowance
                db.execute("DELETE FROM api_calls WHERE at=? AND model=?", (stamp, model))
        try:
            error = json.loads(e.read().decode()).get("error", {})
            message = error.get("message", "")[:220]  # Google's message never contains our key
            if e.code == 429 and "perday" in re.sub(r"[_\s]", "", json.dumps(error.get("details", []))).lower():  # QuotaFailure quotaId
                message += " [%s]" % DAILY_QUOTA
        except Exception:
            message = ""
        text = "Gemini HTTP %d (%s)%s" % (e.code, model, ": " + message if message else "")
        if e.code in (401, 403) or (e.code == 400 and re.search(r"api[ _]?key", message, re.I)):
            raise KeyRejected(text) from None
        raise ValueError(text) from None
    except Exception:
        # Timeout or dropped connection. Analysis and voice generation have no side effects, so this is retried like an overload;
        # the row is removed so retries cannot exhaust the local daily allowance.
        with store.transaction() as db:
            db.execute("DELETE FROM api_calls WHERE at=? AND model=?", (stamp, model))
        raise ValueError("Gemini HTTP 504 (%s): no response in time" % model) from None
    store.key_accepted()  # Google answered: whatever was wrong with the key is not any more
    return data


def call_with_fallback(store, cfg, key, chain_default, fn, rounds=4, waits=(10, 30, 60), budget=240):
    """Run fn(model) with the configured model, then the fallback chain when Google says a model is gone (404) or overloaded (429/5xx).
    Overload is retried after a short wait; if it persists, Transient is raised so the job is re-queued, never marked broken.
    A model that works instead of a configured one that is GONE (404) is remembered so later calls go straight to it; one that merely
    worked while the configured model was busy is not (a passing 429 once left the analysis on a weaker model for good: it was the one
    that wrote a runaway answer). When every model that failed has its day's quota used up (a 429 marked DAILY_QUOTA) the rounds are not
    waited for: the wait would be for tomorrow. A per-minute 429 reads the same and is waited for like any other overload."""
    chain = [cfg[key]] + [m for m in chain_default if m != cfg[key]]
    last = None
    transient = busy = exhausted = False
    gone, rejected = set(), None
    deadline = time.time() + budget  # one call never holds the worker (and n8n's HTTP request) longer than the budget
    for rnd in range(rounds):
        transient = busy = exhausted = False
        for model in chain:
            if time.time() > deadline and last is not None:
                raise Transient("Gemini không phản hồi kịp (%ds), sẽ thử lại sau: %s" % (budget, last))
            try:
                result = fn(model)
            except KeyRejected as e:  # this model refuses the key: a key can lack access to one model while the fallbacks work
                rejected = rejected or e
                continue
            except ValueError as e:
                text = str(e)
                if "HTTP 404" in text:
                    gone.add(model)
                    last = e
                    continue
                if any("HTTP %d" % c in text for c in TRANSIENT):
                    last = e
                    transient = True
                    if "HTTP 429" in text and DAILY_QUOTA in text:
                        exhausted = True
                    else:
                        busy = True
                    continue
                raise
            if model != cfg[key] and cfg[key] in gone:
                with store.transaction() as db:
                    db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(model), key))
                cfg[key] = model
            return result
        if not busy:  # nothing failed that waiting could mend
            break
        if rnd < rounds - 1:
            time.sleep(min(waits[rnd], max(0, deadline - time.time())))
    if rejected and not transient:
        raise rejected  # every model that answered refused the key: the key is the problem, whatever else failed on the way
    if transient:
        raise Transient(
            ("Hạn mức Gemini của khóa đã hết, sẽ thử lại sau: " if exhausted and not busy else "Gemini đang quá tải, sẽ thử lại sau: ")
            + str(last)
        )
    raise last


def generate(store, cfg, parts, schema=None, rounds=4, budget=240):
    """One structured Gemini call. If the API rejects the schema (HTTP 400) retry once without it; the strict local validator still applies.
    `rounds` and `budget` bound how long a busy model is waited for (see call_with_fallback)."""
    # maxOutputTokens: a model stuck repeating itself would otherwise write until the API's own limit (hundreds of KB) into our validators
    gen = {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": 16384}
    if schema:
        gen["responseSchema"] = schema
    body = {"contents": [{"parts": parts}], "generationConfig": gen}

    def attempt(model):
        try:
            return gemini(store, model, body)
        except ValueError as e:
            if gen.get("responseSchema") and "HTTP 400" in str(e):
                gen.pop("responseSchema")
                return gemini(store, model, body)
            raise

    return call_with_fallback(store, cfg, "model", MODEL_FALLBACKS, attempt, rounds=rounds, budget=budget)
