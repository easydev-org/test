"""Push tick-by-tick progress into a check run, then finish it.

Live-ish without a cookie: the workflow owns a check run and PATCHes its text every few seconds,
so the newest content is available to any reader with a PAT — no web session, no App.
"""
import json
import os
import time
import urllib.error
import urllib.request

TOKEN = os.environ["GH_TOKEN"]
REPO = os.environ["REPO"]
SHA = os.environ["SHA"]
API = "https://api.github.com/repos/" + REPO


def call(path, method="GET", body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer " + TOKEN,
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        raw = r.read()
        return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:250]


print("repo=%s sha=%s" % (REPO, SHA[:10]))
status, cr = call("/check-runs", "POST", {
    "name": "app-push-probe",
    "head_sha": SHA,
    "status": "in_progress",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "output": {"title": "streaming", "summary": "started", "text": "line 0"},
})
print("create check run ->", status)
if status not in (200, 201):
    print(" ", cr)
    raise SystemExit("cannot create a check run")

cr_id = cr["id"]
print("check run id:", cr_id)

lines = ["line 0"]
for i in range(1, 6):
    time.sleep(4)
    lines.append("tick %d at %s" % (i, time.strftime("%H:%M:%S", time.gmtime())))
    body = "\n".join(lines)
    st, res = call("/check-runs/%d" % cr_id, "PATCH", {
        "output": {"title": "streaming", "summary": "live (%d ticks)" % i, "text": body},
    })
    print("patch %d -> %s (text %d chars)" % (i, st, len(body)))
    if st != 200:
        print("  ", res)

st, _ = call("/check-runs/%d" % cr_id, "PATCH", {
    "status": "completed", "conclusion": "success",
    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
})
print("complete ->", st)
print("CHECK_RUN_ID=%d" % cr_id)
