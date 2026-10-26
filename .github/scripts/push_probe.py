"""Write to output.text, then READ IT BACK IMMEDIATELY, from inside the workflow.

The previous run reported patch -> 200 five times, summary came back, and text came back None. Two
explanations fit that:

    a) the write went somewhere else (a field I did not mean), or
    b) GitHub does not return output.text on read, at least not to this token.

Only a read from the SAME token that wrote it separates them. So this creates a check run, patches
each field separately, and GETs after each write, printing exactly what came back.
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


def show(tag, cr_id):
    """Print exactly what a GET returns for output, field by field."""
    st, d = call("/check-runs/%d" % cr_id)
    o = d.get("output") or {}
    print("%-18s GET=%s title=%r summary_len=%d text_len=%d text=%r"
          % (tag, st, o.get("title"), len(o.get("summary") or ""),
             len(o.get("text") or ""), (o.get("text") or "")[:60]))
    return d


print("repo=%s sha=%s" % (REPO, SHA[:10]))

# --- 1. create with ALL three fields set -------------------------------------
st, cr = call("/check-runs", "POST", {
    "name": "text-where-probe",
    "head_sha": SHA,
    "status": "in_progress",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "output": {
        "title": "TITLE-AT-CREATE",
        "summary": "SUMMARY-AT-CREATE",
        "text": "TEXT-AT-CREATE-MARKER",
    },
})
print("create ->", st)
if st not in (200, 201):
    print(" ", cr)
    raise SystemExit("cannot create")
cr_id = cr["id"]
print("check run id:", cr_id)
show("after create", cr_id)

# --- 2. patch ONLY text, then read ------------------------------------------
st, _ = call("/check-runs/%d" % cr_id, "PATCH", {
    "output": {"title": "TITLE-PATCH-1", "summary": "SUMMARY-PATCH-1",
               "text": "TEXT-PATCH-1-MARKER"},
})
print("\npatch1 ->", st)
show("after patch1", cr_id)

# --- 3. patch summary only, leaving text out — does text survive? -----------
st, _ = call("/check-runs/%d" % cr_id, "PATCH", {
    "output": {"title": "TITLE-PATCH-2", "summary": "SUMMARY-PATCH-2"},
})
print("\npatch2 (no text field) ->", st)
show("after patch2", cr_id)

# --- 4. how long is text allowed? try a long one ----------------------------
big = "\n".join("log line %05d" % i for i in range(2000))
print("\nlong text chars:", len(big))
st, res = call("/check-runs/%d" % cr_id, "PATCH", {
    "output": {"title": "TITLE-PATCH-3", "summary": "SUMMARY-PATCH-3", "text": big},
})
print("patch3 (long) ->", st, "" if st == 200 else res)
show("after patch3", cr_id)

# --- 5. finish, then read again --------------------------------------------
st, _ = call("/check-runs/%d" % cr_id, "PATCH", {
    "status": "completed", "conclusion": "success",
    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
})
print("\ncomplete ->", st)
show("after complete", cr_id)

print("\nCHECK_RUN_ID=%d" % cr_id)
