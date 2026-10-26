"""Measure the two limits that decide whether this scales.

  a) SIZE    how many characters of text fit before PATCH is refused.
  b) RATE    how fast may a single check run be PATCHed before GitHub says no.

The failure mode of (b) matters: is it a 429 to back off from, or a silent drop?
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
        return r.status, json.loads(raw) if raw else {}, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300], dict(e.headers)


st, cr, _ = call("/check-runs", "POST", {
    "name": "limits-probe",
    "head_sha": SHA,
    "status": "in_progress",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "output": {"title": "limits", "summary": "probing", "text": "start"},
})
if st not in (200, 201):
    raise SystemExit("create failed: %s %s" % (st, cr))
cr_id = cr["id"]
print("check run id:", cr_id, flush=True)

print("\n=== a) how much text fits ===", flush=True)
for target in (30000, 60000, 65535, 70000, 120000):
    text = ("x" * 99 + "\n") * (target // 100)
    st, res, _ = call("/check-runs/%d" % cr_id, "PATCH", {
        "output": {"title": "limits", "summary": "size", "text": text},
    })
    stored = -1
    if st == 200:
        st2, got, _ = call("/check-runs/%d" % cr_id)
        stored = len((got.get("output") or {}).get("text") or "")
    print("  sent %6d chars -> PATCH %s, stored %d" % (len(text), st, stored), flush=True)
    if st != 200:
        print("     refusal:", str(res)[:220], flush=True)

call("/check-runs/%d" % cr_id, "PATCH", {
    "output": {"title": "limits", "summary": "rate", "text": "rate test"},
})

print("\n=== b) how fast may one check run be PATCHed ===", flush=True)
ok = 0
first_fail = None
t0 = time.monotonic()
for i in range(40):
    st, res, hdrs = call("/check-runs/%d" % cr_id, "PATCH", {
        "output": {"title": "limits", "summary": "burst %d" % i, "text": "burst %d" % i},
    })
    if st == 200:
        ok += 1
    else:
        first_fail = (i, st, str(res)[:140],
                      {k: v for k, v in hdrs.items()
                       if "rate" in k.lower() or "retry" in k.lower()})
        break
elapsed = time.monotonic() - t0
print("  %d successful PATCHes in %.1fs" % (ok, elapsed), flush=True)
if first_fail:
    print("  first refusal at #%d: %s" % (first_fail[0], first_fail[1]), flush=True)
    print("  body:", first_fail[2], flush=True)
    print("  rate headers:", first_fail[3], flush=True)
else:
    print("  no refusal within 40 rapid PATCHes", flush=True)

call("/check-runs/%d" % cr_id, "PATCH", {
    "status": "completed", "conclusion": "success",
    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "output": {"title": "limits", "summary": "done", "text": "done"},
})
print("\nLIMITS CHECK_RUN_ID=%d" % cr_id, flush=True)
