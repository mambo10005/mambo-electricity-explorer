"""Compliance exercises for lessons 11 and 12 (ADR 0012). Concept questions tied to records in
content/responsibilities.yaml; the snapshot is the record set's fingerprint, so editing a record
gives new questions and invalidates old answers.

Rules the tests enforce:
- a question about what a source says cites existing records (its claim-to-source link);
  questions about this app's own teaching framework cite none and say so;
- where organizations overlap (OVERLAP), the correct option names more than one source, so
  no question forces a single-organization answer;
- applicability questions (UNRESOLVED) never have a "yes, it applies" answer;
- synthetic organizations and their internal policies are labeled SYNTHETIC, and no
  fictional requirement is attributed to a real authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from mambo_explorer import responsibilities
from mambo_explorer.exercises import Exercise, _order

CALCULATION_ID = "responsibility_records"
SYNTHETIC_ORG = "Riverside Example Power (SYNTHETIC company)"
SYNTHETIC_POLICY = (
    "SYNTHETIC internal policy SYN-1, written by the company itself (not by any authority): "
    "log every grid disturbance within one business day, and review the log for each "
    "calendar month."
)


@dataclass(frozen=True)
class Spec:
    question: str
    correct: str
    decoys: tuple[str, str, str]
    explanation: str
    records: tuple[str, ...]


SPECS: dict[str, Spec] = {
    # --- lesson 11: who sets the rules? ---------------------------------------------------
    "wholesale_definition": Spec(
        "Under Federal Power Act section 201, which sale falls within its wholesale provision?",
        "A sale of electric energy to any person for resale, in interstate commerce",
        (
            "Every sale of electricity in the United States",
            "A sale to a household for its own use",
            "Only sales made by a system operator",
        ),
        "Section 201 defines a wholesale sale as a sale to any person for resale, and covers "
        "such sales in interstate commerce. It says this part of the Act does not apply to any "
        "other sale, except as it specifically provides. Whether a real sale is interstate is a "
        "separate question the section alone does not settle.",
        ("ferc-wholesale-sales", "ferc-not-other-sales"),
    ),
    "operator_vs_overseer": Spec(
        "ERCOT describes scheduling power on its grid and settling the competitive wholesale "
        "market. On that same page, whom does ERCOT name as overseeing it?",
        "The Public Utility Commission of Texas and the Texas Legislature",
        (
            "ERCOT says it oversees itself",
            "The California Public Utilities Commission",
            "The page says no one oversees ERCOT",
        ),
        "A system operator (ERCOT) and the bodies it names as overseeing it are different "
        "roles. The page does not mention FERC or NERC; this lesson draws no conclusion about "
        "their roles in ERCOT, and that question is recorded as unresolved.",
        ("ercot-wholesale-settlement",),
    ),
    "who_complies_reliability": Spec(
        "Under FPA section 215 and 18 CFR 40.1, who must comply with approved reliability "
        "standards?",
        "Users, owners, and operators of the bulk-power system, with each standard naming the "
        "subset it covers",
        (
            "Only market operators such as ISOs",
            "Every retail electricity customer",
            "Only organizations with 'reliability' in their name",
        ),
        "The statute names users, owners, and operators of the bulk-power system (outside "
        "Alaska and Hawaii), and the regulation requires each standard to identify the subset "
        "it applies to. So the answer for one organization and one standard needs that "
        "standard's text, not a label.",
        ("ferc-reliability-oversight", "standards-name-their-subset"),
    ),
    "layers_new_england": Spec(
        "A company trading in New England's wholesale electricity markets wants to read the "
        "rules. Which sources are relevant to investigate?",
        "More than one: ISO-NE's tariff (Market Rule 1) and the Federal Power Act provisions "
        "on wholesale sales",
        (
            "Only the ISO-NE tariff; federal law has nothing to do with it",
            "Only the Federal Power Act; tariffs do not matter",
            "Only the California Public Utilities Commission's rules",
        ),
        "Rules come in layers. ISO-NE's page says Market Rule 1 governs the New England "
        "wholesale markets and that FERC created and authorized the tariff; Federal Power Act "
        "section 201 covers wholesale sales in interstate commerce. Which provisions bind a "
        "particular company depends on facts not given here.",
        ("iso-ne-market-rule-1", "ferc-wholesale-sales"),
    ),
    "roles_differ": Spec(
        "Which statement is supported by the sources cited in this lesson?",
        "Roles differ: ERCOT describes scheduling power, while FPA section 215 gives the "
        "reliability framework no authority to order generation or transmission to be built",
        (
            "Every regulator dispatches power plants",
            "The electric reliability organization sets wholesale electricity prices",
            "The California Public Utilities Commission schedules power on ERCOT's grid",
        ),
        "None of the other statements is supported by the cited sources. Regulators, system "
        "operators, and reliability organizations do different things, and not every "
        "institution dispatches generators or sets prices.",
        ("ercot-wholesale-settlement", "ferc-reliability-oversight"),
    ),
    # --- lesson 12: from a requirement to evidence ----------------------------------------
    "chain_order": Spec(
        "Which order follows a requirement from its source to a fix?",
        "Source → applicability questions → requirement → control → evidence → review → "
        "remediation",
        (
            "Requirement → evidence → source → control → review → remediation → applicability "
            "questions",
            "Control → evidence → source → requirement → applicability questions → review → "
            "remediation",
            "Evidence → review → remediation → source → applicability questions → requirement "
            "→ control",
        ),
        "Start from the official source, ask whether and how it could apply, state the exact "
        "requirement, design a control, keep evidence that the control ran, review that "
        "evidence, and fix what the review finds.",
        (),
    ),
    "label_not_applicability": Spec(
        f"{SYNTHETIC_ORG} calls one of its teams 'grid operations'. Does that title show "
        "whether the company must file Form DOE-417?",
        "No conclusion is possible from a title: read the current form's own criteria and "
        "have a qualified person decide",
        (
            "Yes: any team called 'grid operations' must file",
            "Yes: every company located in the United States files it",
            "No: only DOE itself files the form",
        ),
        "The 2023 notice this app read does not list who must file or say whether filing is "
        "mandatory, and the current form was not available. A title, a label, or a location "
        "never decides applicability; the source is something to investigate.",
        ("doe-417-collection",),
    ),
    "evidence_period": Spec(
        f"{SYNTHETIC_POLICY} To show the March review happened, the company offers a review "
        "record dated and covering April. What does it show?",
        "It does not show March was covered: the evidence is for a different period",
        (
            "Yes: any review record counts for any month",
            "Yes, as long as the April record is detailed",
            "It shows the company is certified",
        ),
        "Evidence must match both the requirement and the period. A record for April is not "
        "evidence for March. (SYN-1 is a synthetic internal policy, not a rule of any "
        "authority.)",
        (),
    ),
    "test_not_approval": Spec(
        "This app's automated tests pass and its calculators' checks match. What does that show?",
        "Only that the software behaves as its own tests expect; it is not certification or "
        "regulatory approval",
        (
            "That a regulator approved the app",
            "That a company using the app is certified as compliant",
            "That every source in the explorer applies to the user",
        ),
        "A passing test or a verified model result is evidence about software, checked "
        "against the app's own expectations. Certification and approval come from the "
        "responsible authority, and compliance conclusions need human review.",
        (),
    ),
    "proposal_not_effective": Spec(
        "In September 2025 FERC published a proposal to approve Reliability Standard "
        "CIP-003-11. What did that proposal by itself make effective?",
        "Nothing: a proposal is not effective. A later final rule (Order No. 918) carried an "
        "effective date",
        (
            "CIP-003-11, from the day the proposal was published",
            "CIP-003-11, from the day comments closed",
            "CIP-003-11, from the day this app retrieved the proposal",
        ),
        "Order No. 918, published 2026-03-24, states it is effective 2026-05-26. That is the "
        "final rule's date; the standard's own enforceable date follows its implementation "
        "plan, which was not read. A retrieval date is never an effective date.",
        ("cip-003-11-proposal", "cip-003-11-final"),
    ),
    "after_review": Spec(
        f"{SYNTHETIC_POLICY} The monthly review finds two disturbances that were never "
        "logged. What is the next step in the chain?",
        "Remediation: correct the log and the control that missed them, record what was done, "
        "and review again",
        (
            "Delete the two disturbances from the review notes",
            "Mark the policy as met, because most events were logged",
            "Nothing: the app's tests passed",
        ),
        "Review exists to find gaps; remediation fixes both the record and the control, and "
        "the fix is itself reviewed. (SYN-1 is a synthetic internal policy.)",
        (),
    ),
}
GENERATORS = tuple(SPECS)
# Questions where more than one organization's source is relevant at once.
OVERLAP = ("layers_new_england",)
# Questions about whether something applies; no option may conclude "yes, it applies".
UNRESOLVED = ("label_not_applicability",)


def snapshot_id() -> str:
    return f"compliance-{responsibilities.load().fingerprint}"


def generate(spec: dict) -> Exercise:
    s = SPECS[spec["generator"]]
    cat = responsibilities.load()
    for record_id in s.records:
        cat.record(record_id)  # raises StopIteration if a cited record disappeared
    snap = snapshot_id()
    options, answer = _order(snap + spec["exercise_id"], s.correct, list(s.decoys))
    sources = (
        "Sources: "
        + "; ".join(cat.sources[cat.record(r)["source_reference"]]["title"] for r in s.records)
        + "."
        if s.records
        else "Educational summary written for this app; not taken from an official source."
    )
    return Exercise(
        spec["exercise_id"],
        snap,
        s.question,
        options,
        answer,
        f"{s.explanation} {sources}",
        CALCULATION_ID,
        synthetic=SYNTHETIC_ORG in s.question or "SYNTHETIC" in s.question,
    )
