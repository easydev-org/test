"""Keep a check run's text growing for 90 seconds, so an OUTSIDE reader can poll it mid-job.

This is the only test that answers the question: is the text readable while the job is still
running, or does GitHub only serve it once the job completes?

The workflow does nothing else, so the job is in_progress for the whole window. A reader with a
PAT polls GET /check-runs/{id} from another machine and records what it sees.

Two details learned earlier and applied here:
  - every PATCH carries the FULL text, because output is replaced wholesale, not merged
  - the last PATCH sets status/conclusion but still carries the text, or it would be erased
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
        return e.code, e.read().decode("utf-8", "replace")[:300]


CR_NAME = "live-read-probe"

st, cr = call("/check-runs", "POST", {
    "name": CR_NAME,
    "head_sha": SHA,
    "status": "in_progress",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "output": {"title": "live", "summary": "0 lines", "text": "start"},
})
print("create ->", st)
if st not in (200, 201):
    print(" ", cr)
    raise SystemExit("create failed")
cr_id = cr["id"]
# Print this early and loudly: the outside poller needs it, and buffering would hide it.
print("CHECK_RUN_ID=%d" % cr_id, flush=True)

lines = ["start"]
for i in range(1, 16):
    time.sleep(6)
    lines.append("line %02d at %s" % (i, time.strftime("%H:%M:%S", time.gmtime())))
    st, _ = call("/check-runs/%d" % cr_id, "PATCH", {
        "status": "in_progress",
        "output": {"title": "live", "summary": "%d lines" % len(lines),
                   "text": "\n".join(lines)},
    })
    print("patch %02d -> %s (total %d lines)" % (i, st, len(lines)), flush=True)

# Finish WITHOUT dropping the text.
st, _ = call("/check-runs/%d" % cr_id, "PATCH", {
    "status": "completed", "conclusion": "success",
    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "output": {"title": "live", "summary": "%d lines" % len(lines),
               "text": "\n".join(lines)},
})
print("complete ->", st, flush=True)
print("DONE CHECK_RUN_ID=%d" % cr_id, flush=True)
