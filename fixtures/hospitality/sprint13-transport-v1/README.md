# Sprint 13 synthetic transport fixture

This authored snapshot copies the approved synthetic local-guide catalog shape and adds only synthetic transport fields. It does not describe a real hotel or provider.

- TR-01 has 4 passenger seats excluding the driver, 2 luggage units, and a synthetic one-way per-vehicle price of VND 180,000. The independent 5-passenger expectation is `not_fit` on seat capacity.
- TR-02 has 6 passenger seats, unknown luggage capacity, and synthetic one-way per-person price VND 45,000. For 3 passengers, server-calculated `total_amount` is VND 135,000.
- Only TR-01 has an approved synthetic provider contact URL; it uses `https://example.com/synthetic/providers/tr-01`.
- License, insurance, rental eligibility, and current availability remain unknown.
