# 0012 — Regulatory responsibility records and introductory compliance learning

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

The Compliance section was a placeholder. Beginners need to know which organizations set
which rules before any compliance work makes sense. The obvious failure is an app that
seems to tell someone "this rule applies to you". That is a legal conclusion, and it
depends on facts, the current text, and qualified review. A second failure is presenting
a proposal, or the date someone read a page, as an effective rule.

## Source review (2026-10-11)

Readable and used:
- Federal Power Act sections 201 and 215 (16 U.S.C. 824 and 824o) and Commodity Exchange
  Act section 2 (7 U.S.C. 2), from GovInfo's United States Code, 2023 edition;
- 18 CFR 40.1, from eCFR;
- Federal Register documents 2025-18396 (CIP-003-11 proposal), 2026-05711 (Order No. 918),
  and 2023-18729 (DOE-417 notice), read through GovInfo copies and the Federal Register API;
- the CPUC's About page and its Resource Adequacy page (California-specific);
- ERCOT's About page;
- ISO-NE's tariff index page.

Not readable, and **not bypassed**:
- ferc.gov returned HTTP 403;
- nerc.com and texasre.org returned no readable content;
- cftc.gov showed a human-verification page;
- DOE's OE-417 pages returned a missing page or a DNS failure;
- puc.texas.gov returned HTTP 402;
- federalregister.gov document pages redirected to a verification page.

Content was narrowed to what the readable sources support. The gaps are listed in the
records file and shown on the Compliance page.

## Decision

1. **Versioned records** (`content/responsibilities.yaml`, set v1.0.0; validated by
   `responsibilities.py` on every load).
   - **Fields.** Each record maps one paraphrased claim to one source section: authority,
     organization type, activity, jurisdiction scope, supported responsibility, explicit
     limitations, source reference, section, version, published and effective dates,
     retrieval date, and human review status.
   - **Status labels.** Records are labeled binding requirement, approved tariff or rule,
     official guidance, educational summary, or proposed change. The label must match the
     source's document type.
   - **Dates.** Unknown dates are null. An effective date needs a quoted basis and a
     published date on or before it. A proposal can never carry an effective date. A
     retrieval date is never used as an effective date.
   - **Wording.** Text that concludes applicability ("you must…", "applies to you") is
     rejected.
   - **Review.** Records are unreviewed. An AI agent cannot be recorded as a reviewer.
2. **Explorer** (Compliance page, COMP-02).
   - **Navigation.** By activity: wholesale transactions, retail service, reliability,
     emergency reporting, procurement, and financial derivatives.
   - **Each entry** reads "Relevant source to investigate" and shows its source link,
     section, version, dates, limitations, and review status.
   - **Overlaps.** Several organizations can appear for one activity, and related records
     are linked.
   - **Also shown:** unresolved questions (ERCOT and federal roles; CIP-003-11 rule vs
     standard dates; DOE-417 version; CFTC/FERC boundary), a claim-to-source map, and the
     source gaps.
   - **Local only.** Content is local; nothing is fetched or crawled.
3. **Lessons 11 and 12** (COMP-03).
   - **Claims.** A new optional `claims` field lists record ids. The validator requires each
     claim's source to appear in the lesson's sources, and each compliance exercise's cited
     records to be among the lesson's claims.
   - **Exercises.** Exercises of kind `compliance` (`compliance_exercises.py`) take their
     snapshot from the record set's fingerprint, so editing a record invalidates old
     answers.
   - **Overlaps.** Overlap questions require "more than one" source.
   - **Applicability.** Applicability questions never answer "yes".
   - **Synthetic organization.** Lesson 12 uses a SYNTHETIC company and its own invented
     internal policy. It attributes no requirement to a real authority.
4. **Out of scope:** an applicability engine, filings, certification, deadline
   calculation, evidence uploads or storage, and new data collection. COMP-01 (a maintained
   effective-dated rules database) and COMP-04 (operational compliance) stay planned.

## Consequences

- A person can see which sources to read and why, but never gets an answer to "does
  this apply to me".
- Records are a point-in-time snapshot (retrieved 2026-10-11). They are not monitored for
  changes, and keeping them current needs a person.
- All records, both lessons, and the 20 new glossary terms are agent-authored and
  unreviewed (BL-3).
- ERCOT's relationship to federal provisions is deliberately left unresolved until sources
  that address it can be read.
