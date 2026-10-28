"""Ollama vision client and the background tagging worker (stdlib only for HTTP)."""
import base64
import json
import logging
import os
import threading
import urllib.error
import urllib.request

from . import db, images, tags

log = logging.getLogger("wardrobe.tagger")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.74.81.122:11434").rstrip("/")
MODEL = os.environ.get("WARDROBE_MODEL", "gemma4:12b-it-qat")
TIMEOUT_S = 180
IDLE_S = 5
OFFLINE_RETRY_S = 300

state = {"offline": False, "error": ""}
wake = threading.Event()


class Offline(Exception):
    """Ollama can't be reached or can't serve the model; the item stays pending."""


def build_request(jpeg):
    return {
        "model": MODEL,
        "stream": False,
        "think": False,
        "format": tags.json_schema(),
        "messages": [{"role": "user", "content": tags.PROMPT,
                      "images": [base64.b64encode(jpeg).decode()]}],
    }


def ask(jpeg):
    body = json.dumps(build_request(jpeg)).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            reply = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise Offline(f"Ollama HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Offline(str(e)) from None
    msg = reply.get("message") if isinstance(reply, dict) else None
    return msg.get("content") if isinstance(msg, dict) else None


def tag_one(con, item, data_dir):
    path = os.path.join(data_dir, "photos", item["photo"])
    try:
        with open(path, "rb") as f:
            jpeg = images.tag_image(f.read())
    except (OSError, images.BadImage) as e:
        db.set_failed(con, item["id"], f"Couldn't read the photo: {e}")
        return
    content = ask(jpeg)  # may raise Offline
    try:
        result = tags.parse_reply(content)
    except tags.TagError as e:
        db.set_failed(con, item["id"], str(e))
        return
    db.set_tagged(con, item["id"], result, MODEL)


def run(db_path, data_dir):
    """Worker loop: never exits, never raises."""
    while True:
        delay = IDLE_S
        try:
            con = db.connect(db_path)
            try:
                item = db.next_pending(con)
                if item:
                    tag_one(con, item, data_dir)
                    state.update(offline=False, error="")
                    delay = 0
            finally:
                con.close()
        except Offline as e:
            state.update(offline=True, error=str(e))
            log.warning("tagger offline, retry in %ds: %s", OFFLINE_RETRY_S, e)
            delay = OFFLINE_RETRY_S
        except Exception:  # noqa: BLE001 - keep the worker alive
            log.exception("tagger error")
            delay = 30
        if delay:
            wake.wait(delay)
            wake.clear()


def start(db_path, data_dir):
    t = threading.Thread(target=run, args=(db_path, data_dir), daemon=True, name="tagger")
    t.start()
    return t
