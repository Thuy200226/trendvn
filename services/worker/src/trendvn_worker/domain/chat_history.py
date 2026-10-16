"""Present legacy duplicate empty search attempts as one result, retaining every selected candidate."""


def search_messages(messages, picked):
    latest = {}
    for message in messages:
        if message["kind"] != "videos":
            continue
        body = message["body"]
        key = (message["account"], body.get("product"), body.get("source"), body.get("account_username"))
        if body.get("product") is not None:
            latest[key] = message["id"]
    visible = []
    for message in messages:
        if message["kind"] == "login":
            continue
        body = message["body"]
        key = (message["account"], body.get("product"), body.get("source"), body.get("account_username"))
        if (
            message["kind"] == "videos"
            and message["state"] in ("done", "error")
            and not body.get("results")
            and not picked.get(str(message["id"]))
            and latest.get(key, message["id"]) != message["id"]
        ):
            continue
        visible.append(message)
    return visible
