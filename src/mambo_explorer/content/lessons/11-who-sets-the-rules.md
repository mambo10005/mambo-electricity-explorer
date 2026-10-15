---
lesson_id: who-sets-the-rules
title: Who sets the rules?
order: 11
sequence_stage: compliance
prerequisites: [power-vs-energy]
objectives:
  - Tell a regulator apart from a system operator, and a reliability organization apart from a market operator.
  - Explain the difference between a wholesale sale and a retail sale, as federal law defines the wholesale side.
  - Explain why federal and state bodies can both be relevant to the same activity, for different parts of it.
  - Recognize that rules come in layers (statutes, regulations, standards, tariffs) and that more than one layer can be relevant at once.
  - Explain why a job title, a market label, or a location alone never decides which rules apply.
content_version: 1.0.0
effective_date: 2026-10-11
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: fpa-201
    title: 16 U.S.C. 824 (Federal Power Act section 201), GovInfo, United States Code 2023 edition
    url: https://www.govinfo.gov/content/pkg/USCODE-2023-title16/html/USCODE-2023-title16-chap12-subchapII-sec824.htm
    accessed: 2026-10-11
  - id: fpa-215
    title: 16 U.S.C. 824o (Federal Power Act section 215), GovInfo, United States Code 2023 edition
    url: https://www.govinfo.gov/content/pkg/USCODE-2023-title16/html/USCODE-2023-title16-chap12-subchapII-sec824o.htm
    accessed: 2026-10-11
  - id: cfr-18-40-1
    title: 18 CFR 40.1, eCFR
    url: https://www.ecfr.gov/current/title-18/chapter-I/subchapter-B/part-40/section-40.1
    accessed: 2026-10-11
  - id: ercot-about
    title: ERCOT, About ERCOT
    url: https://www.ercot.com/about
    accessed: 2026-10-11
  - id: iso-ne-tariff
    title: ISO-NE, Transmission, Markets, and Services Tariff (index page)
    url: https://www.iso-ne.com/participate/rules-procedures/tariff
    accessed: 2026-10-11
  - id: cpuc-about
    title: CPUC, About the CPUC
    url: https://www.cpuc.ca.gov/about-cpuc
    accessed: 2026-10-11
  - id: fr-2025-18396
    title: FERC proposed rule on CIP-003-11 (names NERC as the certified ERO), Federal Register 2025-18396 via GovInfo
    url: https://www.govinfo.gov/content/pkg/FR-2025-09-23/html/2025-18396.htm
    accessed: 2026-10-11
  - id: cea-2
    title: 7 U.S.C. 2 (Commodity Exchange Act section 2), GovInfo, United States Code 2023 edition
    url: https://www.govinfo.gov/content/pkg/USCODE-2023-title7/html/USCODE-2023-title7-chap1-sec2.htm
    accessed: 2026-10-11
dataset_bindings: []
calculation_ids: [responsibility_records]
data_panels: []
claims:
  - ferc-wholesale-sales
  - ferc-not-other-sales
  - cpuc-utility-service
  - ercot-wholesale-settlement
  - iso-ne-market-rule-1
  - ferc-reliability-oversight
  - standards-name-their-subset
  - ero-develops-standards
  - regional-entity-enforcement
  - cftc-swaps-futures
  - cea-ferc-state-savings
exercises:
  - exercise_id: wholesale-definition
    kind: compliance
    generator: wholesale_definition
    calculation_id: responsibility_records
  - exercise_id: operator-vs-overseer
    kind: compliance
    generator: operator_vs_overseer
    calculation_id: responsibility_records
  - exercise_id: who-complies-reliability
    kind: compliance
    generator: who_complies_reliability
    calculation_id: responsibility_records
  - exercise_id: layers-new-england
    kind: compliance
    generator: layers_new_england
    calculation_id: responsibility_records
  - exercise_id: roles-differ
    kind: compliance
    generator: roles_differ
    calculation_id: responsibility_records
glossary_terms: [Regulator, System operator, Electric reliability organization, Regional entity, Bulk-power system, Reliability standard, Wholesale sale, Retail sale, Tariff, Rule layers, Applicability, FERC, ERCOT, Dispatch]
limitations:
  - Educational only. Nothing here is legal advice or decides whether any rule applies to anyone.
  - Several official websites (FERC, NERC, the Texas Reliability Entity, the CFTC, the Public Utility Commission of Texas, and DOE's form pages) could not be read on 2026-10-11, so the lesson relies on statutes, regulations, and a few organizations' own pages.
  - California and New England appear as examples only. Other states and regions differ.
  - How federal wholesale and reliability provisions apply inside ERCOT is not settled by the sources used here and is left open.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

Electricity rules are not written by one organization. Different bodies do different jobs,
and several can be relevant to the same activity at the same time. This lesson sorts out a
few of those roles using official sources. Every claim it makes is listed with its source
in the table under *Claims and their sources*.

**Regulator or system operator?** A *regulator* oversees an activity under authority that
a law gives it. A *system operator* runs the grid day to day. ERCOT, for example, describes
itself as scheduling power on the grid it manages and settling the competitive wholesale
market. On the same page it names the Public Utility Commission of Texas and the Texas
Legislature as overseeing it. Running the grid and overseeing the operator are different
roles.

**Reliability organization or market operator?** Under section 215 of the Federal Power
Act (FPA), FERC certifies an *electric reliability organization* (ERO). The ERO proposes
reliability standards, and FERC may approve them. FERC's documents name NERC as that
organization. The statute also defines *regional entities* that can enforce those
standards. Reliability standards are about keeping the bulk-power system working. They are
not market prices, and section 215 says it gives no authority to order new power plants or
transmission lines to be built. A market operator such as ISO New England (ISO-NE), by
contrast, runs markets under a *tariff*. ISO-NE says its Market Rule 1 governs the New
England wholesale markets.

**Wholesale or retail?** FPA section 201 covers *wholesale* sales of electricity in
interstate commerce, and it defines a wholesale sale as a sale to someone who will resell
it. The same section says this part of the Act does not apply to any other sale, except as
it specifically provides. Selling to people who use the electricity themselves is *retail*.
States oversee much of that. The California Public Utilities Commission (CPUC), for
example, describes its mission as making sure Californians have safe, reliable utility
service at reasonable rates. That is one state, and other states have their own
commissions and laws.

**Rules come in layers.** A statute (such as the FPA) gives an authority its powers. A
regulation (such as 18 CFR 40.1) sets out how the authority uses them. A standard or a
tariff then holds the detailed requirements. A company trading in New England's wholesale
markets could have reasons to read both ISO-NE's tariff and the FPA. Financial contracts add
another layer. The Commodity Exchange Act gives the Commodity Futures Trading Commission
(CFTC) jurisdiction over swaps and futures, while also keeping certain FERC and state
authority over agreements made under approved tariffs. Where those layers meet is not
decided here.

**Why a label never decides.** 18 CFR 40.1 says each reliability standard must identify
which users, owners, and operators of the bulk-power system it applies to. So a job title
("grid operations"), a market label ("participant"), or a location ("Texas") is not enough
to know which rules apply. You need the current text of the specific rule, the facts, and a
qualified person's review. The **Compliance** page lists these sources as *relevant sources
to investigate*, never as conclusions.

## Technical detail

- **FPA section 201, 16 U.S.C. 824(b)(1) and (d).** Part II covers transmission in
  interstate commerce and wholesale sales in interstate commerce. "Sale at wholesale" means a
  sale to any person for resale. The section also says that, except as specifically
  provided, the Part does not apply to any other sale of electric energy. Whether a given
  sale is in interstate commerce is a factual and legal question the definition alone does
  not answer. This lesson makes no claim about how these provisions apply in ERCOT.
- **FPA section 215, 16 U.S.C. 824o.**
  - (b)(1): all users, owners, and operators of the bulk-power system must comply with
    approved reliability standards.
  - (c): FERC certifies the ERO.
  - (d)(2): FERC may approve standards the ERO proposes.
  - (e): ERO penalties are subject to FERC review.
  - (a)(7) and (e)(4): define regional entities with delegated enforcement authority.
  - (i)(2): no authority to order construction of generation or transmission.
  - (k): excludes Alaska and Hawaii.

  The statute does not name NERC; FERC's 2025 Federal Register proposal on CIP-003-11 does.
- **18 CFR 40.1(a)–(b).** The Part applies to users, owners, and operators of the
  bulk-power system in the United States (other than Alaska or Hawaii). Each standard must
  identify the subset it applies to.
- **ISO-NE tariff index page.** It lists Section I (General Terms), Section II (open access
  transmission tariff), Section III (Market Rule 1, governing the New England wholesale
  markets), and Section IV (funding). Only the index page was read. Its section dates are
  not treated as effective dates.
- **Commodity Exchange Act, 7 U.S.C. 2(a)(1)(A) and (I).**
  - (A) gives the CFTC exclusive jurisdiction over swaps and futures, with exceptions in the
    Act.
  - (I)(i) keeps FERC and state authority over certain agreements entered into under
    approved tariffs or rate schedules.
  - (I)(ii) keeps the CFTC's own authority.

  Which governs a particular product is unresolved here.
- **Gaps.** ferc.gov returned an access error. nerc.com and the Texas Reliability Entity
  returned no readable content. cftc.gov showed a human-verification page, which was not
  bypassed. The Public Utility Commission of Texas site returned an error. The content was
  narrowed to what the readable sources support.
