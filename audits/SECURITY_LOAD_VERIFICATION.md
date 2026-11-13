# Security load verification — 13 November 2026

Final accepted coverage: **37 scenarios, 37,037 HTTP requests**. Every latest scenario passed its database-state checks, with no HTTP 5xx/transport failures, captured application/database errors, or foreign-key violations. Both main and users databases passed integrity checks with foreign keys enabled.

Each wave released 1,001 clients together, with up to 32 active server handlers. This is not 1,001 simultaneously executing database writers.

## Preserved execution history

There were 48 measured waves (48,048 requests), including targeted reruns. The first broad round exposed 8 cutter and 2 supplier duplicate-request lock timeouts. These returned retryable HTTP 503, not HTTP 500; the saved row counts were still correct. Committed retries were unnecessarily taking the writer lock. The read-only replay fix and second under-lock check removed this contention in all eight affected replay-path reruns. The failed attempts remain in the original JSON.

| Evidence | Waves | Requests | Failed waves |
| --- | ---: | ---: | ---: |
| [load_security_complete_results.json](load_security_complete_results.json) | 37 | 37,037 | 2 |
| [load_account_fingerprint_verified.json](load_account_fingerprint_verified.json) | 2 | 2,002 | 0 |
| [load_legacy_return_followup_verified.json](load_legacy_return_followup_verified.json) | 1 | 1,001 | 0 |
| [load_replay_fastpath_verified.json](load_replay_fastpath_verified.json) | 8 | 8,008 | 0 |

The acceptance table uses the latest targeted result for a repeated scenario; it does not relabel the earlier failures as passes.

Raw HTTP totals, including earlier failed attempts: `{"200":14581,"302":31168,"400":936,"404":36,"409":1000,"410":317,"503":10}`.
Latest accepted HTTP totals: `{"200":10578,"302":24170,"400":936,"404":36,"409":1000,"410":317}`.

## Latest accepted scenario results

| Scenario | Evidence | HTTP responses | Verified database state |
| --- | --- | --- | --- |
| manual_duplicate | [load_replay_fastpath_verified.json](load_replay_fastpath_verified.json) | `{"200":1001}` | `{"rows":1,"expected":1}` |
| manual_unique | [load_security_complete_results.json](load_security_complete_results.json) | `{"200":1001}` | `{"rows":1001,"expected":1001}` |
| return_duplicate | [load_replay_fastpath_verified.json](load_replay_fastpath_verified.json) | `{"200":1001}` | `{"returned":1,"rows":1,"expected":1}` |
| return_competing | [load_security_complete_results.json](load_security_complete_results.json) | `{"200":100,"400":901}` | `{"returned":100,"rows":100,"expected":100}` |
| product_duplicate | [load_replay_fastpath_verified.json](load_replay_fastpath_verified.json) | `{"302":1001}` | `{"rows":2,"expected":2,"missing":[]}` |
| product_unique | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1002,"expected":1002,"missing":[]}` |
| outworker_duplicate | [load_replay_fastpath_verified.json](load_replay_fastpath_verified.json) | `{"302":1001}` | `{"rows":2,"expected":2}` |
| outworker_unique | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1002,"expected":1002}` |
| user_create | [load_account_fingerprint_verified.json](load_account_fingerprint_verified.json) | `{"302":1001}` | `{"rows":3,"expected":3}` |
| user_update | [load_account_fingerprint_verified.json](load_account_fingerprint_verified.json) | `{"302":1001}` | `{"state_ok":true,"audit_rows":1,"expected_audit_rows":1}` |
| user_disable | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"state_ok":true,"audit_rows":1,"expected_audit_rows":1}` |
| user_enable | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"state_ok":true,"audit_rows":1,"expected_audit_rows":1}` |
| user_delete | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"state_ok":true,"audit_rows":1,"expected_audit_rows":1}` |
| rates | [load_security_complete_results.json](load_security_complete_results.json) | `{"200":1000,"302":1}` | `{"rows":1,"expected":1}` |
| advance_duplicate | [load_replay_fastpath_verified.json](load_replay_fastpath_verified.json) | `{"200":1000,"302":1}` | `{"rows":1,"expected":1}` |
| advance_unique | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1001,"expected":1001}` |
| recover_single | [load_security_complete_results.json](load_security_complete_results.json) | `{"200":1000,"302":1}` | `{"balance":0,"receipts":1}` |
| recover_batch | [load_security_complete_results.json](load_security_complete_results.json) | `{"200":1000,"302":1}` | `{"balance":0,"receipts":1}` |
| payroll | [load_security_complete_results.json](load_security_complete_results.json) | `{"200":1000,"302":1}` | `{"payrolls":1,"paid_pieces":10,"gross_paise":5500,"advance_remaining_paise":10000}` |
| edit_product | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1,"expected":1}` |
| edit_outworker | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1,"expected":1}` |
| edit_jobcard | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1,"expected":1}` |
| legacy_scan | [load_security_complete_results.json](load_security_complete_results.json) | `{"200":1,"409":1000}` | `{"rows":1,"expected":1}` |
| legacy_inventory | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1,"expected":1}` |
| legacy_cutter | [load_replay_fastpath_verified.json](load_replay_fastpath_verified.json) | `{"302":1001}` | `{"rows":2,"expected":2}` |
| legacy_supplier | [load_replay_fastpath_verified.json](load_replay_fastpath_verified.json) | `{"302":1001}` | `{"rows":2,"expected":2}` |
| route_sweep | [load_security_complete_results.json](load_security_complete_results.json) | `{"200":473,"302":140,"400":35,"404":36,"410":317}` | `{"rows":1,"expected":1}` |
| alias_collision | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"products":2,"expected":2,"ambiguous_aliases":0}` |
| rate_remove | [load_security_complete_results.json](load_security_complete_results.json) | `{"200":1000,"302":1}` | `{"rows":0,"expected":0}` |
| assign_return | [load_legacy_return_followup_verified.json](load_legacy_return_followup_verified.json) | `{"200":1001}` | `{"jobcard":"1","audit_rows":1}` |
| legacy_edit_bale | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1,"expected":1}` |
| legacy_edit_lump | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1,"expected":1}` |
| legacy_edit_bundle | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1,"expected":1}` |
| legacy_edit_cutter | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1,"expected":1}` |
| legacy_edit_party | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"rows":1,"expected":1}` |
| kept_duplicate | [load_replay_fastpath_verified.json](load_replay_fastpath_verified.json) | `{"302":1001}` | `{"kept_records":1,"advances":1,"amount_to_recover_paise":24000,"returned":48,"kept":2,"remaining":0,"payable":50}` |
| kept_competing | [load_security_complete_results.json](load_security_complete_results.json) | `{"302":1001}` | `{"kept_records":1,"advances":1,"amount_to_recover_paise":24000,"returned":48,"kept":2,"remaining":0,"payable":50}` |

## What this establishes

- An identical manual-job retry saves exactly one job and returns the original receipt. Independent request keys intentionally create independent jobs, even when contents match.
- Unique product and outworker creation saves every expected entry; the product verifier checks for missing names.
- Competing returns, payroll, direct advance recovery, edits and retained-stock charges cannot consume or pay the same tested balance twice.
- Changed-payload same-key conflicts, forged cookies, stale sessions, negative/orphan writes and oversized quantities are also covered by the separate Python security regressions.
- The mixed route sweep covers 57 registered route/method combinations (including the Bootstrap asset lookup) within its single 1,001-request wave. It is not a fresh 1,001-request wave for every route/method. Validation 400/404 and disabled-workflow 410 responses are expected there.

## Scope and deployment

All mutation data is temporary and printer calls are mocked. Production data was not stress-tested or rewritten. Historical failure artifacts have been retained. This verifies the named scenarios and listed weaknesses, not unlimited-load availability or every possible vulnerability.

Clients must reuse the same request key for retries. A deliberately new request key is a new logical submission; this is not content-based deduplication of legitimate repeated jobs.

WAL still permits only one SQLite writer. A persistent external lock or exhausted resources can correctly return retryable 503 for a new write. Such a response must not be interpreted as successful saving; retry the same key. Completed replays no longer require a writer lock, verified under a held unrelated lock.

The default instance databases were inspected read-only and still need the startup upgrades. Back up both databases, then restart the app. Existing login cookies are revoked by the authentication-identity upgrade. See [SECURITY_FIX_VERIFICATION.md](SECURITY_FIX_VERIFICATION.md) for the finding-by-finding changes and verification counts.

