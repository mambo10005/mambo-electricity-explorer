---
lesson_id: requirement-to-evidence
title: From a requirement to evidence
order: 12
sequence_stage: compliance
prerequisites: [who-sets-the-rules]
objectives:
  - Follow the chain from an official source through applicability questions, a requirement, a control, evidence, review, and remediation.
  - Explain why applicability is a question to investigate, not something a title, label, or location decides.
  - Check that evidence matches both the requirement and the period it is meant to cover.
  - Tell a proposal apart from an effective requirement, and a retrieval date apart from an effective date.
  - Explain why a model result is not certification and an app test is not regulatory approval.
content_version: 1.0.0
effective_date: 2026-10-11
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: fr-2023-18729
    title: DOE/EIA notice on Form DOE-417, Federal Register 2023-18729 via GovInfo
    url: https://www.govinfo.gov/content/pkg/FR-2023-08-30/html/2023-18729.htm
    accessed: 2026-10-11
  - id: fr-2025-18396
    title: FERC proposed rule on CIP-003-11, Federal Register 2025-18396 via GovInfo
    url: https://www.govinfo.gov/content/pkg/FR-2025-09-23/html/2025-18396.htm
    accessed: 2026-10-11
  - id: fr-2026-05711
    title: FERC Order No. 918 (final rule) on CIP-003-11, Federal Register 2026-05711 via GovInfo
    url: https://www.govinfo.gov/content/pkg/FR-2026-03-24/html/2026-05711.htm
    accessed: 2026-10-11
  - id: cfr-18-40-1
    title: 18 CFR 40.1, eCFR
    url: https://www.ecfr.gov/current/title-18/chapter-I/subchapter-B/part-40/section-40.1
    accessed: 2026-10-11
dataset_bindings: []
calculation_ids: [responsibility_records]
data_panels: []
claims:
  - doe-417-collection
  - cip-003-11-proposal
  - cip-003-11-final
  - standards-name-their-subset
exercises:
  - exercise_id: chain-order
    kind: compliance
    generator: chain_order
    calculation_id: responsibility_records
  - exercise_id: label-not-applicability
    kind: compliance
    generator: label_not_applicability
    calculation_id: responsibility_records
  - exercise_id: evidence-period
    kind: compliance
    generator: evidence_period
    calculation_id: responsibility_records
  - exercise_id: proposal-not-effective
    kind: compliance
    generator: proposal_not_effective
    calculation_id: responsibility_records
  - exercise_id: test-not-approval
    kind: compliance
    generator: test_not_approval
    calculation_id: responsibility_records
  - exercise_id: after-review
    kind: compliance
    generator: after_review
    calculation_id: responsibility_records
glossary_terms: [Applicability, Requirement, Control, Evidence, Compliance review, Remediation, Proposed rule, Effective date, Retrieval date, Reliability standard, Synthetic]
limitations:
  - Educational only. Nothing here is legal advice, an applicability decision, a filing, or a certification.
  - Riverside Example Power and its policy SYN-1 are SYNTHETIC. SYN-1 is the company's own invented internal policy; it is not a requirement of DOE, FERC, or any other authority.
  - Form DOE-417 is used only as an example of a real source to investigate. The lesson does not say who must file it or whether filing is mandatory; the current form was not available.
  - No deadlines are calculated and no evidence is stored. Nothing typed here is saved except exercise progress.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

Knowing that a rule exists is only the first step. Compliance work follows a chain, and
each link needs its own care:

1. **Source.** Start from the official text, at the version that is in force. A proposal
   is not in force.
2. **Applicability questions.** Ask whether, and how, the source could apply. Who does it
   name? Which activities, facilities, or thresholds? Which period? A job title, a market
   label, or a location never answers this on its own.
3. **Requirement.** Write down exactly what the source requires, in its own terms.
4. **Control.** Decide what the organization does to meet it: a procedure, a check, a
   system.
5. **Evidence.** Keep records showing the control actually ran. They must cover the same
   requirement and the same period.
6. **Review.** A qualified person checks the evidence against the requirement.
7. **Remediation.** Fix what the review finds, both the record and the control, and review
   again.

**A synthetic example.** *Riverside Example Power* is a **SYNTHETIC** company invented for
this lesson. It has written its own internal policy, **SYN-1**: log every grid disturbance
within one business day and review the log for each calendar month. SYN-1 is not a rule of
any authority. It only shows how a requirement becomes a control and evidence.

Suppose Riverside wants to show the March review happened. A review record covering April
does not do it, because the evidence must match the period. If the March review finds two
disturbances that were never logged, the next step is remediation, not deleting the finding.

**A real source to investigate.** The U.S. Department of Energy uses Form DOE-417 (Electric
Emergency Incident and Disturbance Report) to monitor electric emergencies and disturbances.
In 2023 it asked for comments on changes to the form. That notice is a *source to
investigate*. It does not tell you whether Riverside, or anyone else, must file. Answering
that needs the current form, its own criteria, and a qualified person.

**Proposed versus effective.** In September 2025 FERC published a *proposal* to approve
reliability standard CIP-003-11. The proposal made nothing effective. A later final rule,
Order No. 918, was published on 2026-03-24 and states that it is effective 2026-05-26. Even
that date belongs to the final rule. The standard's own enforceable date follows its
implementation plan. The day someone *retrieved* a document is never its effective date.

**What software can and cannot show.** When this app's tests pass, or a model run passes
its checks, that shows the software behaved as its own tests expect. It is not
certification, not regulatory approval, and not a compliance conclusion. Those come from the
responsible authority and need human review.

## Technical detail

- **Applicability lives in the source.** 18 CFR 40.1(b) requires each reliability standard
  to identify the subset of users, owners, and operators it applies to. An applicability
  answer therefore needs the specific standard's text and the organization's facts. The
  explorer never computes one.
- **DOE-417 (Federal Register 2023-18729, published 2023-08-30).**
  - The notice requests a three-year extension, with changes, of Form DOE-417 (OMB
    1901-0288).
  - It says the changes keep the form aligned with NERC standards CIP-008-6 and EOP-004-6.
  - It estimates the number of respondents but does not list who must file or say whether
    filing is mandatory.
  - DOE's current form pages were unreachable on 2026-10-11, so the version in force is
    unverified.
- **CIP-003-11.**
  - Proposal: Federal Register 2025-18396, published 2025-09-23, comments due 2025-11-24,
    Docket RM25-8-000.
  - Final rule: Order No. 918, Federal Register 2026-05711, published 2026-03-24. Its DATES
    line says the action is effective May 26, 2026. It approves the standard, its
    implementation plan, and its effective date, and retires CIP-003-10 when CIP-003-11
    takes effect.

  The explorer shows the two as separate records. The proposal has no effective date.
- **Evidence matching.** A piece of evidence supports a requirement only for the
  requirement it addresses and the period it covers. Matching on topic alone ("it is a
  review log") is not enough.
- **Out of scope here.** Deadline calculation, evidence uploads or storage, filings,
  certification, and applicability engines. Lesson progress is the only thing saved.
