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
  poll.py findings POLL         the findings as they stand now, and the misses
  poll.py missed   POLL "what the reviewers missed" --found-by ci|user|test|advisor|poll|other [--note TEXT]
      Record a defect in the reviewed work that surfaced later and no reviewer reported,
      as M1, M2, ... in <poll>/missed.jsonl.
  poll.py stats    [--since YYYY-MM-DD] [--kind K] [--by model-effort|model|provider|slot|kind] [--pairs] [--json]
      How each group of runs did over every poll in the polls folder: runs, problems by
      category, time, tokens, cost, and the verdicts on what it found. --pairs puts side
      by side the polls that ran two slots of one provider, which is the fair comparison.

Everything here only reads the polls, except the commands that record something,
which append to files of their own in the poll folder. Nothing here starts a model.
"""
import argparse
import fcntl
import json
import os
import re
import sys
import time

import poll as P

VERDICTS = ("confirmed", "refuted", "not-taken", "unverified")
SEVERITIES = ("high", "medium", "low")
HOW = ("test", "code", "compiler", "reasoning", "other")
FOUND_BY = ("ci", "user", "test", "advisor", "poll", "other")
FINDINGS = "findings.jsonl"
MISSED = "missed.jsonl"


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


def misses_of(root):
    return [r for r in records(os.path.join(root, MISSED)) if r.get("type") == "miss"]


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


def cmd_missed(a):
    root = P.poll_dir(a.poll)
    P.meta_of(root)
    if not a.what.strip():
        P.die("say what the reviewers missed")
    path = os.path.join(root, MISSED)
    rec = append(path, lambda old: stamp({"type": "miss", "id": next_id(old, "miss", "M"), "what": a.what.strip(),
                                          "found_by": a.found_by, "note": a.note}))
    print("recorded %s: %s" % (rec["id"], path))


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
    missed = misses_of(root)
    if missed:
        print("\nMissed by every reviewer, found later:\n")
        print("| id | found by | what | note |")
        print("| --- | --- | --- | --- |")
        for r in missed:
            print("| %s |" % " | ".join(P.cell(r.get(k) or "") for k in ("id", "found_by", "what", "note")))


# ---------------------------------------------------------------- reading every poll

def poll_day(pid):
    """YYYY-MM-DD of a poll id, "" when the id carries no date."""
    m = re.match(r"(\d{4})(\d{2})(\d{2})-\d{6}", pid)
    return "-".join(m.groups()) if m else ""


def all_polls(notes):
    """(root, meta) of every poll under the polls folder. Reads only: it takes no lock, and a
    folder that is not a readable poll is noted and skipped instead of stopping the scan."""
    base = os.path.realpath(P.POLLS)
    out = []
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        root = os.path.join(base, name)
        if os.path.islink(root) or not os.path.isdir(root):
            continue
        try:
            with open(os.path.join(root, "poll.json")) as f:
                meta = json.load(f)
        except (OSError, ValueError):
            notes.append("%s: no readable poll.json, skipped" % name)
            continue
        if not P.meta_ok(meta):
            notes.append("%s: poll.json names an unknown model, skipped" % name)
            continue
        out.append((root, meta))
    return out


def slot_dirs(root, meta, notes):
    """(slot, folder) of the poll's slots whose folder is a real folder inside the poll."""
    out = []
    for m in meta["models"]:
        d = os.path.join(root, m)
        if os.path.islink(d) or not os.path.isdir(d):
            notes.append("%s/%s: no folder, skipped" % (os.path.basename(root), m))
            continue
        out.append((m, d))
    return out


def record_of(root, meta, m, d):
    """The slot's run record: its run.json when there is one, else worked out in memory from its files."""
    rec = P.read_run(d)
    if rec is not None:
        return rec
    info = P.slot_info(meta, m)
    rec = {"slot": m, "provider": info["provider"], "model": info["model"], "effort": info["effort"],
           "effort_source": info.get("effort_source"), "inferred": True,
           "source": "poll.json" if info["model"] else "none: run backfill"}
    rec.update(P.observe(info["provider"], d))
    return rec


# ---------------------------------------------------------------- stats

BY = {   # how runs are grouped: provider + model + effort by default
    "model-effort": lambda r, meta: (r["provider"], r.get("model") or "?", effort_label(r)),
    "model": lambda r, meta: (r["provider"], r.get("model") or "?"),
    "provider": lambda r, meta: (r["provider"],),
    "slot": lambda r, meta: (r["slot"],),
    "kind": lambda r, meta: (meta.get("kind") or "unknown",),
}
REASONING_ON_TOP = {"deepseek", "gemini"}   # their usage counts reasoning apart from output (see usage)


def effort_label(r):
    return r.get("effort") or ("default" if r.get("effort_source") == "cli-default" else "?")


def tokens(r):
    """Tokens a run spent, cached input left out: input + output, plus reasoning where it is counted apart."""
    parts = [r.get("input"), r.get("output")] + ([r.get("reasoning")] if r.get("provider") in REASONING_ON_TOP else [])
    return None if any(type(v) is not int for v in parts) else sum(parts)


def median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def short(n):
    if n is None:
        return "?"
    return "%.1fM" % (n / 1e6) if n >= 1e6 else "%.0fk" % (n / 1e3) if n >= 1e3 else "%d" % n


def ratio(n, d, fmt="%.2f"):
    return fmt % (n / d) if d else "-"


def verdicts(fs):
    return {v: sum(1 for f in fs if f.get("verdict") == v) for v in VERDICTS}


def credit(found, keys):
    """Each finding once per group that reported it: its slot or a slot named in --also."""
    out = {}
    for f in found:
        for k in {keys[s] for s in [f.get("slot")] + list(f.get("also") or []) if s in keys}:
            out.setdefault(k, []).append(f)
    return out


def gather(a, notes):
    """Ended runs with their records, grouped, and the polls they came from."""
    polls, groups, pairs = [], {}, []
    counts = {"run.json": 0, "in memory": 0, "running": 0}
    for root, meta in all_polls(notes):
        day = poll_day(meta.get("id") or os.path.basename(root))
        if a.since and (not day or day < a.since) or a.kind and meta.get("kind") != a.kind:
            continue
        found = fold(records(os.path.join(root, FINDINGS)))
        missed = misses_of(root)
        covered = bool(found or missed)
        runs = {}
        for m, d in slot_dirs(root, meta, notes):
            rec = record_of(root, meta, m, d)
            if rec.get("status") in ("running", "not started"):
                counts["running"] += rec.get("status") == "running"
                continue
            counts["in memory" if rec.get("inferred") and not os.path.exists(os.path.join(d, P.RUN)) else "run.json"] += 1
            runs[m] = rec
        if not runs:
            continue
        pid = os.path.basename(root)
        polls.append({"id": pid, "covered": covered})
        keys = {m: BY[a.by](r, meta) for m, r in runs.items()}
        credited = credit(found, keys)
        confirmed_here = sum(1 for f in found if f.get("verdict") == "confirmed")
        for m, r in runs.items():
            g = groups.setdefault(keys[m], {"polls": set(), "covered": set(), "runs": [], "found": [],
                                            "recall_base": 0, "inferred": False})
            g["runs"].append(dict(r, poll=pid, covered=covered))
            g["inferred"] |= bool(r.get("inferred"))
            if pid not in g["polls"]:
                g["polls"].add(pid)
                g["recall_base"] += confirmed_here + len(missed)
                g["found"] += credited.get(keys[m], [])
                if covered:
                    g["covered"].add(pid)
        by_provider = {}
        for m, r in runs.items():
            by_provider.setdefault(r["provider"], []).append(m)
        for provider, ms in sorted(by_provider.items()):
            if len(ms) > 1:                              # two configurations, one brief: the fair comparison
                own = credit(found, {m: m for m in ms})
                pairs.append({"poll": pid, "provider": provider, "covered": covered,
                              "slots": [dict(slot_summary(runs[m], own.get(m, [])), slot=m) for m in ms]})
    return polls, groups, pairs, counts


def slot_summary(r, found):
    v = verdicts(found)
    return {"model": r.get("model"), "effort": effort_label(r), "status": r.get("status"),
            "failure": r.get("failure"), "minutes": None if r.get("duration_s") is None else round(r["duration_s"] / 60, 1),
            "tokens": tokens(r), "usd": r.get("usd"), "verdicts": v,
            "unique_confirmed": sum(1 for f in found if f.get("verdict") == "confirmed" and not f.get("also")),
            "inferred": bool(r.get("inferred"))}


def per_finding(values, conf, show):
    """Cost of one confirmed finding: "" when nothing was spent this way, "?" when no figure is known,
    and a lower bound (≥) when some runs' figures are unknown."""
    if not values:
        return ""
    known = [v for v in values if v is not None]
    if not conf or not known:
        return "-" if not conf else "?"
    return ("≥" if len(known) < len(values) else "") + show(sum(known) / conf)


def summarize(key, g):
    runs = g["runs"]
    fin = [r for r in runs if r.get("status") == "finished"]
    problems = {}
    for r in runs:
        if r.get("failure"):
            problems[r["failure"]] = problems.get(r["failure"], 0) + 1
    toks = [tokens(r) for r in runs if tokens(r) is not None]
    per_token = [r for r in runs if r.get("billing") == "per token"]
    v = verdicts(g["found"])
    conf = v["confirmed"]
    judged = conf + v["refuted"] + v["not-taken"]          # unverified says nothing about precision
    cov = [r for r in runs if r["covered"]]                 # cost per finding only where findings were recorded
    usd_cov = [r.get("usd") for r in cov if r.get("billing") == "per token"]
    plan_tok = [tokens(r) for r in cov if r.get("billing") != "per token"]
    cost = [per_finding(usd_cov, conf, lambda x: "$%.3f" % x), per_finding(plan_tok, conf, lambda x: short(x) + " tok")]
    minutes = [r["duration_s"] / 60 for r in cov if r.get("duration_s") is not None]
    med = median([r["duration_s"] / 60 for r in fin if r.get("duration_s") is not None])
    return {"group": " ".join(key), "inferred": g["inferred"], "polls": len(g["polls"]), "runs": len(runs),
            "finished": len(fin), "problems": problems,
            "median_min": None if med is None else round(med, 1),
            "tokens_sum": sum(toks) if toks else None, "tokens_median": median(toks),
            "usd_known": round(sum(r["usd"] for r in per_token if r.get("usd") is not None), 4) if per_token else None,
            "usd_unknown_runs": sum(1 for r in per_token if r.get("usd") is None),
            "covered_polls": len(g["covered"]), "verdicts": v,
            "precision": round(conf / judged, 2) if judged else None,
            "unique_confirmed": sum(1 for f in g["found"] if f.get("verdict") == "confirmed" and not f.get("also")),
            "recall_proxy": round(conf / g["recall_base"], 2) if g["recall_base"] else None,
            "cost_per_confirmed": " + ".join(c for c in cost if c) or "-",
            "min_per_confirmed": round(sum(minutes) / conf, 1) if conf and minutes else None}


def cmd_stats(a):
    if a.since and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.since):
        P.die("--since takes a date as YYYY-MM-DD")
    notes = []
    polls, groups, pairs, counts = gather(a, notes)
    rows = sorted((summarize(k, g) for k, g in groups.items()), key=lambda s: (-s["runs"], s["group"]))
    if a.json:
        json.dump({"polls": len(polls), "covered_polls": sum(p["covered"] for p in polls), "records": counts,
                   "by": a.by, "groups": rows, "pairs": pairs if a.pairs else None, "notes": notes},
                  sys.stdout, indent=1, ensure_ascii=False)
        print()
        return
    print("Polls: %d, %d with findings or misses recorded. Runs: %d from run.json, %d worked out in memory "
          "(no run.json yet); %d still running, left out." % (
              len(polls), sum(p["covered"] for p in polls), counts["run.json"], counts["in memory"], counts["running"]))
    print("\n| %s | polls | runs | finished | problems | median min | tokens sum / median | USD known | "
          "polls with findings | conf/ref/not-taken/unverif | precision | unique conf | recall proxy | "
          "cost / conf | min / conf |" % a.by)
    print("| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |")
    for s in rows:
        v = s["verdicts"]
        usd = "-" if s["usd_known"] is None else "$%.2f%s" % (s["usd_known"], " (+%d ?)" % s["usd_unknown_runs"]
                                                               if s["usd_unknown_runs"] else "")
        print("| %s |" % " | ".join(P.cell(x) for x in (
            s["group"] + (" *" if s["inferred"] else ""), s["polls"], s["runs"], s["finished"],
            ", ".join("%s %d" % kv for kv in sorted(s["problems"].items())) or "-",
            "-" if s["median_min"] is None else s["median_min"],
            "%s / %s" % (short(s["tokens_sum"]), short(s["tokens_median"])), usd,
            "%d of %d" % (s["covered_polls"], s["polls"]), "/".join(str(v[k]) for k in VERDICTS),
            "-" if s["precision"] is None else s["precision"], s["unique_confirmed"],
            "-" if s["recall_proxy"] is None else s["recall_proxy"], s["cost_per_confirmed"],
            "-" if s["min_per_confirmed"] is None else s["min_per_confirmed"])))
    print("\n* some runs' model or effort was inferred, not recorded at launch; ? means unknown. Tokens leave out "
          "cached input. Precision = confirmed / (confirmed + refuted + not-taken); recall proxy = confirmed / "
          "(confirmed findings of its polls + misses recorded there); cost and minutes per confirmed finding count "
          "only polls with findings recorded (USD for per-token models, tokens for plan models).")
    if a.pairs:
        print("\nPolls that ran two slots of one provider, side by side:\n")
        print("| poll | slot | model | effort | status | min | tokens | USD | conf/ref/not-taken/unverif | unique conf |")
        print("| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |")
        for p in pairs:
            for s in p["slots"]:
                print("| %s |" % " | ".join(P.cell(x) for x in (
                    p["poll"], s["slot"], (s["model"] or "?") + (" *" if s["inferred"] else ""), s["effort"],
                    s["status"] + (" (%s)" % s["failure"] if s["failure"] else ""),
                    "?" if s["minutes"] is None else s["minutes"], short(s["tokens"]),
                    "-" if s["usd"] is None else "$%.3f" % s["usd"],
                    "/".join(str(s["verdicts"][k]) for k in VERDICTS) if p["covered"] else "none recorded",
                    s["unique_confirmed"])))
        if not pairs:
            print("(none)")
    for n in notes:
        print("note: " + n)


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
    p = sub.add_parser("missed")
    p.add_argument("poll")
    p.add_argument("what")
    p.add_argument("--found-by", required=True, choices=FOUND_BY)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_missed)
    p = sub.add_parser("stats")
    p.add_argument("--since", metavar="YYYY-MM-DD")
    p.add_argument("--kind", choices=P.KINDS)
    p.add_argument("--by", choices=sorted(BY), default="model-effort")
    p.add_argument("--pairs", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_stats)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
