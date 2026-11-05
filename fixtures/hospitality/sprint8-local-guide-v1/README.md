# Sprint 8 local guide fixture

All records in this pack are synthetic technical-pilot examples, checked on
2026-10-28 and valid through 2027-03-31 unless a record has an earlier
`valid_to`. They do not represent real venues, transport providers, route
times, hotel review, or hotel approval. Sources are imported staged
(`guest_approved: false`); a dev operator must preview and activate them before
the existing M1 guest repository will serve the facts.

The pack intentionally includes unknown access, allergy and child-safety
suitability; unknown hours and availability; one closed venue; one expired
venue; a sponsored venue; a conflicting hours fact from a second source; two
providers with seats excluding the driver; and exactly four directional route
legs. Missing reverse directions remain missing.

Expected offline priority examples are authored in domain tests, not included
as serving-pack oracle data. Priority A favors the quiet/budget DIN-01 and
ATT-02; priority B favors culture/social DIN-02 and ATT-01, with DIN-02's
sponsored label and hours conflict disclosed. Unknown hard suitability never
passes as supported.
