#!/usr/bin/env python3
"""What came of polls, read or written after they ran: verdicts on findings, and statistics.

poll.py forwards these commands here, so they are written `poll.py <command>`:

  poll.py finding  POLL SLOT "short claim" --verdict confirmed|refuted|not-taken|unverified
                   [--severity high|medium|low] [--also SLOT[,SLOT]] [--how test|code|compiler|reasoning|other]
                   [--note TEXT]
      Record a finding a slot reported, as F1, F2, ... in <poll>/findings.jsonl. --also names
      the other slots that reported the same thing.
  poll.py finding  POLL --update ID [--verdict V] [--severity S] [--also SLOT[,SLOT]] [--how H] [--note TEXT]
      Change a finding later. An update is appended; nothing earlier is rewritten.
  poll.py findings POLL         the findings as they stand now

Everything here only reads the polls, except the commands that record something,
which append to files of their own in the poll folder. Nothing here starts a model.
"""
import argparse
import fcntl
import json
import os
import sys
import time

import poll as P

VERDICTS = ("confirmed", "refuted", "not-taken", "unverified")
SEVERITIES = ("high", "medium", "low")
HOW = ("test", "code", "compiler", "reasoning", "other")
FINDINGS = "findings.jsonl"


def records(path):
    """The JSON objects of a .jsonl file; a line that does not parse is skipped, not fatal."""
    out = []
    for line in P.read(path).splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def append(path, make):
    """Append make(records so far) as one line, under a lock, so two writers never take the same id."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        old = []
        for line in f.read().splitlines():
            try:
                old.append(json.loads(line))
            except ValueError:
                pass
        rec = make([r for r in old if isinstance(r, dict)])
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
    return rec


def stamp(rec):
    now = int(time.time())
    return dict(rec, time=now, time_iso=P.iso(now))


def next_id(old, kind, prefix):
    nums = [int(r["id"][1:]) for r in old if r.get("type") == kind and str(r.get("id", ""))[1:].isdigit()]
    return "%s%d" % (prefix, max(nums, default=0) + 1)


def slots_arg(meta, text):
    """A comma list of slots, each checked against the poll and named by its folder."""
    return [P.find_slot(meta, s.strip()) for s in (text or "").split(",") if s.strip()]


def fold(recs):
    """Findings as they stand: each update applied over the finding it names, in order."""
    out = {}
    for r in recs:
        if r.get("type") == "finding" and r.get("id") not in out:
            out[r["id"]] = dict(r, history=[])
        elif r.get("type") == "update" and r.get("id") in out:
            f = out[r["id"]]
            if r.get("verdict") and r["verdict"] != f.get("verdict"):
                f["history"].append(f.get("verdict"))
            f.update({k: v for k, v in r.items() if k in ("verdict", "severity", "how", "note", "also")})
    return list(out.values())


def findings_of(root):
    return fold(records(os.path.join(root, FINDINGS)))


def cmd_finding(a):
    root = P.poll_dir(a.poll)
    meta = P.meta_of(root)
    path = os.path.join(root, FINDINGS)
    also = slots_arg(meta, a.also) if a.also is not None else None
    if a.update:
        if a.slot or a.claim:
            P.die("--update changes a finding; give no SLOT or claim with it")
        change = {k: v for k, v in (("verdict", a.verdict), ("severity", a.severity), ("how", a.how),
                                    ("note", a.note), ("also", also)) if v is not None}
        if not change:
            P.die("--update needs something to change: --verdict, --severity, --how, --also or --note")

        def make(old):
            if not any(r.get("type") == "finding" and r.get("id") == a.update for r in old):
                P.die("no finding %s in this poll" % a.update)
            return stamp(dict(type="update", id=a.update, **change))
    else:
        if not a.slot or not a.claim:
            P.die('write: finding POLL SLOT "short claim" --verdict ...')
        if not a.verdict:
            P.die("a new finding needs --verdict (%s)" % "|".join(VERDICTS))
        slot = P.find_slot(meta, a.slot)
        if slot in (also or []):
            P.die("--also names the slot that reported the finding")

        def make(old):
            return stamp({"type": "finding", "id": next_id(old, "finding", "F"), "slot": slot,
                          "claim": a.claim.strip(), "verdict": a.verdict, "severity": a.severity,
                          "also": also or [], "how": a.how, "note": a.note})
    rec = append(path, make)
    print("%s %s: %s" % ("updated" if a.update else "recorded", rec["id"], path))


def cmd_findings(a):
    root = P.poll_dir(a.poll)
    found = findings_of(root)
    if not found:
        print("no findings recorded in %s" % root)
    else:
        print("| id | slot | also | verdict | severity | how | claim | note |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for f in found:
            verdict = f.get("verdict") or ""
            if f["history"]:
                verdict += " (was %s)" % ", ".join(str(v) for v in f["history"])
            print("| %s |" % " | ".join(P.cell(v or "") for v in (
                f["id"], f.get("slot"), ", ".join(f.get("also") or []), verdict, f.get("severity"),
                f.get("how"), f.get("claim"), f.get("note"))))
        count = {v: sum(1 for f in found if f.get("verdict") == v) for v in VERDICTS}
        print("\n%d finding(s): %s." % (len(found), ", ".join("%s %d" % kv for kv in count.items())))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="poll.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("finding")
    p.add_argument("poll")
    p.add_argument("slot", nargs="?")
    p.add_argument("claim", nargs="?")
    p.add_argument("--update", metavar="ID")
    p.add_argument("--verdict", choices=VERDICTS)
    p.add_argument("--severity", choices=SEVERITIES)
    p.add_argument("--also", metavar="SLOT[,SLOT]")
    p.add_argument("--how", choices=HOW)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_finding)
    p = sub.add_parser("findings")
    p.add_argument("poll")
    p.set_defaults(fn=cmd_findings)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
