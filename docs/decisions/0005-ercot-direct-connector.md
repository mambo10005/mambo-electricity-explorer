# 0005 — ERCOT direct connector (NP6-345-CD) and namespaced storage

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

PRD R-29 makes ERCOT the first regional operator after EIA. The owner preferred
"Actual System Load by Weather Zone". ERCOT offers two documented ways to get it:
- the **Public API**, which requires an ERCOT API Explorer account, a subscription key,
  and an Azure B2C ID token (an unauthenticated request returns 401)
- the **ercot.com public report pages**, which list each day's document and link to
  it, with no login

No ERCOT account exists. Creating one, or accepting terms on the owner's behalf, is
not allowed.

## Decision

1. **Report:** NP6-345-CD (report type 13101), CSV variant only.
2. **Access:** the ercot.com public listing JSON plus the document download. These are
   the URLs ERCOT's official product page uses for this EMIL-listed Public report.
   They are **not** a documented developer API. Mitigations:
   - strict validation of the listing structure, content types, ZIP layout, and CSV
     header, so any change fails loudly
   - no scraping or other fallback
   - low volume: at most 7 documents and 10 requests per run, with a 1 s pause,
     following Terms of Use §6
   - If the owner registers for the Public API later, a second transport can replace
     this one; this milestone has exactly one.
3. **Storage:** the existing Store, parameterized by `namespace`, `schema`, and
   `identity`.
   - ERCOT lives in `<data_dir>/ercot-np6-345-cd/`, with its own catalog, writer lock,
     and Parquet schema.
   - EIA keeps the default `eia930` namespace with no migration.
   - Shared code paths: atomic writes, the one-transaction commit, revision lineage,
     `latest` view, validate/quarantine, and diagnostics.
   - Additions: `latest_index()` (identity-keyed lookup for any schema) and an
     optional artifact name for `write_raw()`.
4. **Time:** OperDay, HourEnding, and DSTFlag are stored as published and never
   converted, because the file states no time zone. Publication time comes from the
   listing's offset-bearing `PublishDate`.
5. **Units:** not stated by the source, so stored as `"not stated by source"`.
6. **UI:** Explore gets an explicit source selector. The ERCOT view is separate and
   never joined with EIA. Lessons keep their EIA bindings.

## Alternatives considered

- **Public API:** blocked by registration. It would add pagination (`_meta`) and the
  token lifecycle.
- **Scraping the HTML report list (`GetReports.do`):** rejected. The JSON the product
  page loads is structured, and HTML scraping is more brittle.
- **One shared table with a `source` column:** rejected. Different identities
  (period label vs. OperDay/HourEnding/DSTFlag) and different schemas would force
  lossy normalization. It would also put EIA rows at risk from ERCOT writes.

## Consequences

- If ERCOT changes the listing or download URLs, collection stops with a clear error
  until the contract is reviewed again.
- Only about 31 days of history are reachable without the registered API.
- DST behavior, units, and the TOTAL definition stay unverified until observed or
  documented. Their limitations are shown in the UI.
