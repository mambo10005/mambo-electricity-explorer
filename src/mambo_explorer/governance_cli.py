"""`mambo governance`: the local review workspace for M1, AGG-A/B, and CMP-A/B (Stage 26).

Every mutating action previews by default and writes only with --execute, through the
append-only, atomically rewritten event files in `<MAMBO_DATA_DIR>/assumptions/`. Nothing here
infers a reviewer from the account running the command, prints a reviewer's name back, or
chooses a convention, method, or policy on its own.
"""

from __future__ import annotations

import json
import sys

from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot import governance as gv

SETTING_ACTIONS = {
    "set-convention": gv.SET_CONVENTION,
    "set-aggregation": gv.SET_AGGREGATION,
    "set-revision-policy": gv.SET_REVISION_POLICY,
}


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=list))


def _need(args, *names) -> None:
    missing = [n for n in names if not getattr(args, n.replace("-", "_"), None)]
    if missing:
        raise gv.GovernanceError("missing " + ", ".join(f"--{m}" for m in missing))


def _public(ev: ap.Event) -> dict:
    """An event without the reviewer's name (the local file holds it)."""
    d = ap.asdict(ev)
    d["reviewer"] = "(withheld; see the local approvals file)" if d.get("reviewer") else None
    return d


def run(args, settings) -> int:
    data_dir = settings.data_dir
    try:
        return _run(args, data_dir)
    except (gv.GovernanceError, ap.ApprovalError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _run(args, data_dir) -> int:  # noqa: PLR0911
    action = args.action
    if action == "list":
        st = gv.states(data_dir)
        _print(
            [
                {
                    "id": s.id,
                    "version": s.version,
                    "state": s.state,
                    "activation": s.activation,
                    "approval_status": s.approval_status,
                    "dependencies": list(s.dependencies),
                    "selected": s.selected,
                }
                for s in st.values()
            ]
        )
        return 0
    if action == "status":
        st = gv.states(data_dir)
        _print(
            {
                "records": {
                    k: {"state": v.state, "activation": v.activation, "blockers": list(v.blockers)}
                    for k, v in st.items()
                },  # fmt: skip
                "settings": gv.current_settings(data_dir),
                "active_set": gv.active_set(data_dir),
                "stale_downstream": gv.stale_downstream(data_dir),
                "files": {
                    "approvals": str(ap.path(data_dir)),
                    "settings": str(gv.settings_path(data_dir)),
                    "audit": str(gv.audit_path(data_dir)),
                },
            }
        )
        return 0
    if action == "audit":
        _print(gv.audit_entries(data_dir))
        return 0
    if action in SETTING_ACTIONS:
        _need(args, "value", "reviewer", "role", "date", "rationale")
        event = gv.new_setting(
            SETTING_ACTIONS[action], args.value, operator=args.reviewer, role=args.role,
            decided_on=args.date, rationale=args.rationale,
        )  # fmt: skip
        before = gv.current_settings(data_dir)
        print(f"{event['setting']}: {before[event['setting']]} -> {event['value']}")
        stale = gv.stale_downstream(data_dir)
        print(
            "Effect: downstream snapshots recorded under another value become stale (kept, never "
            f"deleted); currently {sum(v['total'] for v in stale.values())} snapshot(s) exist."
        )
        if not args.execute:
            print("Preview: nothing was recorded. Re-run with --execute to append this setting.")
            return 0
        gv.append_setting(data_dir, event)
        gv.audit(data_dir, action, event["setting"], actor_role=event["role"],
                 event_id=event["event_id"], outcome="recorded", detail=event["value"])  # fmt: skip
        print(f"Recorded {event['event_id']} in {gv.settings_path(data_dir)}")
        return 0

    if not args.record_id:
        raise gv.GovernanceError("this action needs a record id (see `mambo governance list`)")
    rec = gv.record(args.record_id)
    rid = rec.id
    if action == "show":
        pkg = gv.review_package(data_dir, rid)
        _print(pkg)
        return 0
    if action == "review":
        pkg = gv.review_package(data_dir, rid)
        _print({k: pkg[k] for k in ("id", "version", "state", "activation", "blockers",
                                     "limitations", "limitations_version", "scope_fingerprint",
                                     "re_review_triggers", "downstream")})  # fmt: skip
        print("To approve, state every item explicitly:")
        print(
            f"  mambo governance approve {rid} --version {rec.version} --scope "
            f"{rec.scope_fingerprint()} --accept-limitations {gv.limitations_version(rid)} "
            f"--acknowledge {','.join(gv.limitation_ids(rid))} --approved-scope HB_NORTH "
            "--triggers record --reviewer <name> --role <role> --date YYYY-MM-DD "
            "--evidence <reference> --rationale <why> [--execute]"
        )
        return 0

    if action == "approve":
        _need(args, "reviewer", "role", "date", "evidence", "rationale", "version", "scope",
              "approved-scope", "accept-limitations", "acknowledge", "triggers")  # fmt: skip
        if args.version != rec.version:
            raise gv.GovernanceError(f"--version must be {rec.version}")
        if args.scope != rec.scope_fingerprint():
            raise gv.GovernanceError(f"--scope must be {rec.scope_fingerprint()} (see `show`)")
        if args.approved_scope != "HB_NORTH":
            raise gv.GovernanceError("--approved-scope must be HB_NORTH (the only governed scope)")
        if args.accept_limitations != gv.limitations_version(rid):
            raise gv.GovernanceError(
                f"--accept-limitations must be the current limitations version "
                f"{gv.limitations_version(rid)}"
            )
        ids = gv.check_acknowledgment(rid, args.acknowledge.split(","))
        triggers = (
            list(rec.re_review_triggers)
            if args.triggers.strip() == "record"
            else [t.strip() for t in args.triggers.split(";") if t.strip()]
        )
        if not triggers:
            raise gv.GovernanceError("--triggers must name at least one re-review trigger")
        fingerprint = getattr(rec, "limitations_fingerprint", None)
        event = ap.new_approval(
            rec,
            reviewer=args.reviewer,
            role=args.role,
            evidence=args.evidence,
            approved_on=args.date,
            accepted_limitations=fingerprint() if fingerprint else None,
            rationale=args.rationale,
            acknowledged_limitations=list(ids),
            approved_scope=args.approved_scope,
            re_review_triggers=triggers,
            evidence_verification_note=args.evidence_verified_note,
            restores=args.restores,
        )
        # the itemized acknowledgment binds to the governance limitations version
        event = ap.Event(**{**ap.asdict(event), "limitations_version": gv.limitations_version(rid)})
        return _finish(args, data_dir, rec, event, "approve")

    if action in ("reject", "request-revision"):
        _need(args, "reviewer", "role", "date", "rationale", "issue")
        kind = ap.KIND_REJECTION if action == "reject" else ap.KIND_REVISION_REQUEST
        event = ap.new_decision(
            rec,
            kind,
            reviewer=args.reviewer,
            role=args.role,
            decided_on=args.date,
            rationale=args.rationale,
            issue=args.issue,
        )
        return _finish(args, data_dir, rec, event, action)
    if action == "no-decision":
        _need(args, "reviewer", "role", "date", "rationale")
        event = ap.new_decision(rec, ap.KIND_NO_DECISION, reviewer=args.reviewer, role=args.role,
                                decided_on=args.date, rationale=args.rationale)  # fmt: skip
        return _finish(args, data_dir, rec, event, action)
    if action == "revoke":
        _need(args, "reviewer", "role", "date", "rationale", "record", "effective-on")
        event = ap.new_revocation(rec, args.record, args.rationale, reviewer=args.reviewer,
                                  role=args.role, effective_on=args.effective_on)  # fmt: skip
        return _finish(args, data_dir, rec, event, action)
    if action == "supersede":
        _need(args, "reviewer", "role", "date", "rationale", "replacement-id",
              "replacement-version", "migration")  # fmt: skip
        event = ap.new_decision(
            rec, ap.KIND_SUPERSESSION, reviewer=args.reviewer, role=args.role,
            decided_on=args.date, rationale=args.rationale, replacement_id=args.replacement_id,
            replacement_version=args.replacement_version, migration=args.migration,
        )  # fmt: skip
        return _finish(args, data_dir, rec, event, action)
    raise gv.GovernanceError(f"unknown action {action!r}")


def _finish(args, data_dir, rec, event: ap.Event, action: str) -> int:
    """Preview the effect, then write (append-only, atomic) and audit only with --execute."""
    before = gv.states(data_dir)[rec.id]
    print(f"{event.kind} {event.record_id} for {rec.id} {rec.version}")
    print(f"Current state: {before.state} ({before.activation})")
    deps = [b for b in before.blockers if b.startswith("dependency:")]
    if action == "approve" and deps:
        print(f"After approval the record would be {gv.INACTIVE_DEPS}: " + "; ".join(deps))
    down = gv.downstream(rec.id)
    if down and action in ("revoke", "reject", "supersede", "request-revision"):
        print(f"Downstream records that would lose their dependency: {', '.join(down)}")
    if action == "approve" and event.evidence_kind == ap.EVIDENCE_PATH:
        verified = "yes, per the reviewer" if event.evidence_verified else "no"
        print(
            f"Evidence: local file found (checksum {event.evidence_checksum}); verified: {verified}"
        )
    elif action == "approve":
        print("Evidence: a reference (not a local file); verified: "
              + ("yes, per the reviewer" if event.evidence_verified else "no"))  # fmt: skip
    if not args.execute:
        print("Preview: nothing was recorded. Re-run with --execute to append this record.")
        return 0
    ap.append(data_dir, event)
    gv.audit(data_dir, action, rec.id, actor_role=event.role, event_id=event.record_id,
             outcome="recorded", detail=(event.rationale or event.reason or ""))  # fmt: skip
    after = gv.states(data_dir)[rec.id]
    print(f"Recorded {event.record_id} in {ap.path(data_dir)}")
    print(f"State now: {after.state} ({after.activation})")
    return 0
