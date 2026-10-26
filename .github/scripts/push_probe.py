"""Leave a check run whose output.text is POPULATED, so a PAT can be tested against it.

Learned the hard way in the previous run: PATCHing {"status": "completed"} with no `output` object
CLEARS the text. So the sequence here finishes WITHOUT touching output, and then does one final
PATCH that carries the full text alongside the completed status.

The point is the artifact at the end: a check run the extension can try to read.
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


CR_NAME = "pat-readable-probe"
TEXT = "\n".join([
    "=== build log ===",
    "step 1: configure .... ok",
    "step 2: compile ...... ok",
    "step 3: test ......... 42 passed",
    "=== end ===",
])

st, cr = call("/check-runs", "POST", {
    "name": CR_NAME,
    "head_sha": SHA,
    "status": "in_progress",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "output": {"title": "pat readable", "summary": "5 lines", "text": TEXT},
})
print("create ->", st)
if st not in (200, 201):
    print(" ", cr)
    raise SystemExit("create failed")
cr_id = cr["id"]
print("check run id:", cr_id)

st, d = call("/check-runs/%d" % cr_id)
o = d.get("output") or {}
print("self-read while in_progress: text_len=%d" % len(o.get("text") or ""))

time.sleep(3)

# Finish it, carrying the SAME text in the same request. Splitting these two is what erased the
# text last time.
st, _ = call("/check-runs/%d" % cr_id, "PATCH", {
    "status": "completed",
    "conclusion": "success",
    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "output": {"title": "pat readable", "summary": "5 lines", "text": TEXT},
})
print("complete+text ->", st)

st, d = call("/check-runs/%d" % cr_id)
o = d.get("output") or {}
print("self-read after completion: text_len=%d" % len(o.get("text") or ""))
print("text:")
for line in (o.get("text") or "(empty)").splitlines():
    print("   ", line)

print("\nCHECK_RUN_ID=%d" % cr_id)
print("PAT_READ_TARGET=%d" % cr_id)
