"""Notify Telegram after the server's local files match a GitHub main update."""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

REPO = "zamwh/gamal-site"
API = f"https://api.github.com/repos/{REPO}"
STATE_KEY = "github_update_notifier"
POLL_SECONDS = 60
MAX_MESSAGE = 3900


def _json_request(url, etag=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gamal-site-update-notifier",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8")), response.headers.get("ETag")
    except urllib.error.HTTPError as error:
        if error.code == 304:
            return None, etag
        raise


def _blob_sha(path):
    with open(path, "rb") as source:
        data = source.read()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _safe_path(root, name):
    if not isinstance(name, str) or not name or os.path.isabs(name):
        return None
    path = os.path.realpath(os.path.join(root, name))
    try:
        if os.path.commonpath((root, path)) != root:
            return None
    except ValueError:
        return None
    return path


def _files_match(root, files):
    if not isinstance(files, list) or not files:
        return False
    for item in files:
        name = item.get("filename")
        path = _safe_path(root, name)
        if path is None:
            return False
        if item.get("status") == "removed":
            if os.path.exists(path):
                return False
            continue
        expected = item.get("sha")
        if not expected or not os.path.isfile(path):
            return False
        try:
            if _blob_sha(path) != expected:
                return False
        except OSError:
            return False
    return True


def _commit_title(item):
    message = (item.get("commit") or {}).get("message") or ""
    return message.splitlines()[0].strip()[:180] or "تحديث بدون عنوان"


def _update_details(head, previous_sha):
    if previous_sha:
        url = f"{API}/compare/{previous_sha}...{head['sha']}"
        try:
            comparison, _ = _json_request(url)
            commits = comparison.get("commits") or []
            files = comparison.get("files") or []
            if commits and files:
                return commits, files
        except urllib.error.HTTPError as error:
            if error.code not in (404, 422):
                raise
    commits = [head]
    files = head.get("files") or []
    return commits, files


def _message(head, commits, files):
    lines = [
        "✅ تم سحب تحديث GitHub والتحقق من تطابق ملفاته على السيرفر.",
        f"المستودع: {REPO}",
        f"النسخة: {head['sha'][:10]}",
        f"التفاصيل: https://github.com/{REPO}/commit/{head['sha']}",
        f"التغييرات ({len(commits)} التزام):",
    ]
    titles = [_commit_title(commit) for commit in commits[-8:]]
    lines.extend("• " + title for title in titles)
    if len(commits) > 8:
        lines.append(f"• وباقي {len(commits) - 8} التزامات أخرى")
    names = [item.get("filename", "") for item in files if item.get("filename")]
    lines.append(f"الملفات التي تغيرت ({len(names)}):")
    lines.extend("• " + name for name in names[:18])
    if len(names) > 18:
        lines.append(f"• و{len(names) - 18} ملفاً آخر")
    return "\n".join(lines)[:MAX_MESSAGE]


class UpdateNotifier:
    def __init__(self, app):
        self.app = app
        self.etag = None
        self.latest = None
        self.pending = None

    def _state(self):
        with self.app.lock:
            return self.app.store.setting(STATE_KEY, {}) or {}

    def _save(self, sha):
        with self.app.lock:
            self.app.store.set_setting(STATE_KEY, {"sha": sha, "checked_at": int(time.time())})

    def check_once(self):
        data, etag = _json_request(f"{API}/commits/main", self.etag)
        self.etag = etag or self.etag
        if data is not None:
            self.latest = data
        head = self.latest
        if not head or not head.get("sha"):
            return
        state = self._state()
        previous = state.get("sha")
        if previous == head["sha"]:
            self.pending = None
            return
        if not self.pending or self.pending.get("head_sha") != head["sha"] or self.pending.get("previous") != previous:
            commits, files = _update_details(head, previous)
            self.pending = {
                "head_sha": head["sha"],
                "previous": previous,
                "commits": commits,
                "files": files,
            }
        root = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
        if not _files_match(root, self.pending["files"]):
            print("update notifier: waiting for server files to match GitHub", head["sha"][:10], flush=True)
            return
        bot = getattr(self.app, "bot", None)
        text = _message(head, self.pending["commits"], self.pending["files"])
        if bot and bot.notify_update(text):
            self._save(head["sha"])
            self.pending = None
        else:
            print("update notifier: Telegram did not confirm delivery; will retry", flush=True)

    def run(self):
        time.sleep(10)
        while True:
            try:
                self.check_once()
            except Exception as error:
                print("update notifier:", type(error).__name__, flush=True)
            time.sleep(POLL_SECONDS)


def start(app):
    worker = UpdateNotifier(app)
    threading.Thread(target=worker.run, daemon=True, name="github-update-notifier").start()
    return worker
