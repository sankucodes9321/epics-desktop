# Quality review

Baseline: 50 offline tests. Reviewed the CLI, privacy package, scripts, tests, build configuration and documentation. Scope is a trusted, single-host college demo. Hardware acceptance is a separate operator task.

| Done | Priority and finding | Effort | Change risk |
|---|---|---|---|
| [x] | High: remove secret-file creation from key setup and rotation. Preserve existing read paths and prove that failed rotations leave encrypted records usable. | Medium | Medium: operator workflow |
| [x] | High: reject invalid reference vectors and ambiguous identities. Bind identification to the complete gallery revision. Bound optimistic retries and validate lockout state. | Medium | Medium: match rejection |
| [x] | High: keep capture children away from secret environment variables and debug sinks. Require provisioned model weights for the supported detector before opening a camera. | Medium | Medium: desktop integration |
| [x] | Medium: prevent unsafe names and spreadsheet formulas in attendance exports, protect export permissions and compatibility with existing labels. | Small | Low: presentation |
| [x] | Medium: align doctor with the active key and timezone, remove full garbage collections from buffer wipes, and strengthen offline test isolation. | Small | Low |
| [x] | High demo value: reconcile evidence and trust claims, document existing local-day behavior, and provide ten ordered hardware acceptance tests in an isolated environment. | Small | Low |

Retain the v1 template format, cosine cutoff, liveness score floor and PipeWire capture sequence. No new inference backend, external service or dependency is needed.


## Results

98 offline tests passed on Python 3.11. The suite uses fake Redis, mocked model and camera entry points, temporary metadata files and synthetic arrays. Ruff, mypy and coverage were unavailable and were skipped. See REVIEW_FINDINGS.md for severity and LIVE_TEST_PLAN.md for operator acceptance. The numbered tests there remain unverified on hardware.

## Desktop delivery

- [x] Add lecture-scoped marking to the watched identification transaction. Keep daily attendance and v1 templates usable.
- [x] Implement recoverable private claims, signed public bulletins, revision-linked corrections, public QR rendering and an independent verifier.
- [x] Build native teacher and student windows, an isolated synthetic mode, evaluation summaries, top-two score-gap measurements and previewed retention.
- [x] Check both windows on a private GTK display. Exercise synthetic enrollment, mark, finalization, file export and verification through the student GUI.
- [x] Run the complete offline suite. It increased from 98 to 122 passing tests during this implementation.

The Fedora teacher and independent Python verifier are implemented. Physical camera cancellation, presentation attacks, real Redis contention, Windows or macOS verification, phone QR scans and native installers remain outside the offline acceptance evidence.
