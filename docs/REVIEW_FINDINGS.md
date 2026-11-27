# Application bug and verification report

## November 20, 2026 review

The original 122 offline tests passed before changes. The updated suite passes 144 offline tests, including 22 new regression cases. A separate integration test uses an actual database server and fresh credentials for every run.

| Area | Problem found | Fix and verification |
|---|---|---|
| Teacher register | Signing a correction left the previous revision and roster on screen. Marking a student could also leave an earlier roster visible. | A successful correction loads the new signed register. A fresh mark invalidates the old view. The native test reviews revision 1, signs an appeal and checks revision 2. |
| Session controls | Marking and publishing were offered in invalid states. A delayed scan could outlive cancellation and overlap a restarted scan loop. | Gate actions on the selected session, required fields and review state. Remove the outstanding scan timer on cancellation or shutdown. The native test starts and cancels repeat scanning, then finalizes the class and checks the available actions. |
| Worker recovery | Once a worker stopped, further button presses kept using the dead pipe. Invalid Redis configuration could also prevent the worker from starting its diagnostics. | Storage initializes on first use. The workspace detects disconnection, offers a restart and reloads sessions. Interrupted requests require a fresh operator action. The native test terminates a synthetic worker and starts a new demonstration through the recovery control. |
| Session discovery | One session from a different signing identity, or a record removed during a Redis scan, could block the entire list. | List each surviving session for the configured signer once. Direct reads still check the signer. Regression coverage includes two signers, duplicate scan results and a disappeared key. |
| Retention | Changing the cutoff left the previous deletion preview visible. An invalid preview could leave a prior confirmation usable. Selection also trusted the stored issuance date before checking its signature. | Clear stale previews, enable deletion only after a matching nonempty preview and validate signed session history during preview and confirmation. Refresh the session picker after deletion. Tests cover changed cutoffs, modified records and signed dates. |
| Trial results | An empty gallery, an unknown identity or a quality rejection could inflate impostor and presentation-test results. Demo evaluation also used a student ID entered on another page. | Require enrollment, give evaluation its own simulated-student field and distinguish identity, liveness and inconclusive outcomes. Aggregate exports include an inconclusive count. Synthetic photo and replay trials report that they cannot establish liveness. |
| Student verification | A previous success remained visible after changing the files, key or trust mode. Boolean and floating-point revision values could compare equal to an integer. A provisional receipt paired with a QR summary gave little guidance. | Both interfaces clear stale results and enable verification when the required inputs are present. Verification checks the revision type, directs preliminary receipt holders to the full register and rejects special files before reading. Error messages keep receipt tokens private. |
| Report exports | A failed CSV write could leave a partial destination that then blocked a retry. Calibration used separate direct-write paths. | Attendance, calibration and classroom exports now share private staging and exclusive publication. A regression test interrupts a CSV export, checks the directory and retries the same filename. |
| Model responses and setup | Malformed crop objects or coordinates produced incidental Python exceptions. Diagnostics required some unused backends while missing invalid detector settings. This installation also lacked CPU PyTorch and both liveness weight files. | Validate detector output before scoring, retain crop cleanup on failure and check the configured backend and weights. Installed the pinned CPU wheel and provisioned the two missing files. Ran all three supported detectors and the recognition model. |

### Interface and maintenance

The teacher workspace now includes a searchable roster, attendance counts, local and UTC timestamps, an expandable correction form, readable scan and trial results, and progress feedback. The student verifier groups each file with its browse action and adapts the school-key field to the selected mode. The cleanup target removes generated project bytecode and pytest caches.

### Verification performed

| Check | Result |
|---|---|
| Offline regression suite | 144 passed. Includes matching, lockout, gallery changes, signed histories, QR payload decoding, quality gates, buffer cleanup and export failures. |
| Native GTK desktop | Passed enrollment, verification, opening a lecture, duplicate scanning, cancellation, roster search, finalization, correction, public QR display, receipt and register export, trial scoring, retention and worker recovery. The independent verifier accepted revision 2 and cleared the result when its input changed. |
| Portable Tk verifier | Passed on a virtual X display in a disposable Linux container. The test selected a register and receipt, switched trust mode, verified inclusion and checked that editing the receipt cleared the previous result. |
| Actual database and CLI | Passed against disposable Valkey 9.0.7. Two simultaneous marks produced one roster entry. Separate processes exported attendance, verified a pre-closure claim, rotated the gallery key and read attendance history after deleting the synthetic enrollment. |
| Container | Built the Dockerfile with rootless Podman. The image ran read-only as UID 10001 with capabilities dropped. It connected to isolated Redis 7.4, listed users, opened and closed a signed class and read its register. The host and image dependency checks passed. |
| Capture and models | Received and cleared the final frame of a real 30-frame GStreamer test-pattern stream. All four cached weights were available. RetinaFace, MTCNN and OpenCV rejected a blank frame with liveness enabled. Facenet512 produced 512 finite values on a synthetic input. |
| Host readiness | The host diagnostic exited successfully. Its Redis ping, template-key check, CPU runtime and PipeWire plugin checks passed. It warned that swap is enabled. |

The tests used synthetic students and disposable storage for all writes. A physical camera, attendance accuracy with people, presentation-attack performance, phone QR scanning, Windows and macOS still require acceptance testing. The live teacher also requires the school's independently provisioned signing seed and public key. Both variables were absent from the review shell.

Use `make test`, `make test-storage` and `make test-desktop` to repeat the regression, server and GTK checks. The [live test plan](LIVE_TEST_PLAN.md) covers hardware acceptance.

## Earlier reviews

| Area | Finding and disposition |
|---|---|
| Camera cleanup | GStreamer now explicitly waits after killing a running child. The Popen context also closes the pipe and waits. A mocked interrupt test checks both calls. Short-read tests check scratch wiping. OpenCV releases the device in finally. |
| Embedding cleanup | Clear the mutable list or writable array returned by represent after copying. Wipe malformed converted vectors and skip malformed crop entries during cleanup so subsequent writable crops are cleared. Test exercises a nonfinite vector. |
| Ownership transfer | sample retains responsibility for its vector until the capture context has exited successfully. Matcher.probe and references wipe in finally, including tag failures. |
| Model errors | A model exception rejects capture. The camera CLI logs fixed diagnostics or the exception type. Untrusted detector confidence and dimensions are validated before numeric logging. |
| Liveness | A filtered candidate with a missing verdict could escape validation. Require every candidate verdict and minimum score. Tests cover filtered candidates, low scores, absent verdicts and exceptions. |
| Redis | Enrollment already watches the user hash. Add first-key binding and authenticated adoption of legacy databases. Concurrent verification checks the counter and the current ciphertext before logging a decision. Identification and attendance now watch those same values before publishing a winning identity. |
| Limits | Python float objects, immutable keys, framework workspaces, native tensors and OS copies cannot be reliably overwritten by Python. A snapshot can miss transient writes. No production camera, model, Redis server or Docker runtime was exercised. |

A simulated interrupt from OpenCV release exposed a local frame that had yet to transfer to the capture context. The OpenCV backend now retains ownership through device release and wipes that frame on exceptional exit. The regression test uses an in-memory camera double.

## Quality review after the local-time change

Severity refers to impact on this single-host demo. These findings came from source inspection and offline regression tests. No live attack or hardware trial was performed.

| Severity | Finding | Fix and offline evidence |
|---|---|---|
| High | Setup and rotation created files containing key material. Deletion through the CLI needed only Redis access. | Retired file generation. Rotate using a separately retained key and authenticate the target record before deletion. Tests cover wrong keys, unchanged history, rotation conflicts, corrupt rows and reuse of v1 data. |
| High | The winning record could stay unchanged while a different enrollment altered the correct identification. Exact ties favored the first user. | Compare per-user maxima and recheck the original gallery revision in the decision transaction. Interleaved enrollments invalidate both winning and unknown decisions; a cross-user tie produces no attendance. |
| High | Validly encrypted abnormal rows could contaminate scoring. A negative cutoff allowed a decision without positive similarity. A low-level decryption caller could retain unauthenticated output. | Validate finite unit-length references after GCM authentication, require positive cutoff and AES-256 keys, and clear failed destinations. Tested altered associated data, wrong keys, NaN, zero and oversized norms. |
| High | Negative or malformed counters weakened lockout or produced unhelpful errors. Redis command errors within EXEC could change related data before reporting failure. Watch retries were unbounded and could replay an uncertain commit. | Validate counters and revisions, watch relevant keys including audit stream type, cap retries and distinguish a confirmed conflict from connection loss. Tests cover racing lockout, corrupt metadata, schema errors and uncertain outcomes. Redis remains a trusted service. |
| High | GStreamer inherited the parent environment, including credentials and debug sink settings. Missing recognition or detector weights could trigger framework provisioning during capture. | Restrict child environment, suppress raw diagnostics and check local weight headers before CLI capture. Tested child invocation, missing weights, malformed cached headers and simulated staging/retry. Authenticity still depends on a trusted cache. |
| Medium | Names could add terminal rows or formula-like spreadsheet cells. Attendance exports inherited the caller's normal file permissions. | Validate new names, escape legacy output and neutralize spreadsheet prefixes. Export exclusively at 0600. Tests verify legacy matching, safe cells, mode and overwrite refusal. |
| Medium | A one-shot unknown returned success. Loops retried persistent operational failures. Doctor validated a different key source than matching. | Unknown returns 2. Only sample rejections and active lockouts continue the loop. Doctor follows active-key precedence and checks configuration. Mocked tests exercise these paths. |
| Low | Full cyclic collection ran on every wipe. Live instructions selected UTC dates despite existing IST support. | Retain immediate overwrites and drop redundant per-buffer heap scans. Correct the guide, retain local-midnight tests and document the ten hardware trials. |

The offline suite started with 50 passing tests. The final review count is recorded in PLAN.md. Native model internals, GPU visibility on target hardware, physical capture, Redis server failure timing, full host write behavior, spoof performance and CPU latency still require live evidence. Older entries above describe the initial implementation; the quality review decisions govern current behavior.

Malformed representation batches now reject the sample and clear all returned mutable embedding lists or arrays. An empty stored key fingerprint is treated as corruption. The backward-compatible adoption path runs only when the fingerprint is absent.

## Session receipts and desktop

Session marking joins the same WATCH/EXEC operation as identity selection and the access entry. Tests cover close-versus-mark conflicts, locked users, repeated scans and recovery of a private claim. Finalization checks the private commitments before signing. Reading a closed register verifies its signed history, counts, roots, predecessor links and private correction commitment. A student-held copy provides an external reference against rollback.

The signed public document omits the roster and private receipt tokens. Tests verify odd and even tree sizes, reject an altered roster or bulletin, exercise live-domain verification with synthetic data, and separate public demo trust from the school identity. File exports use private staging and exclusive publication. A failed export cannot expose a partially written final document. Retention compares the confirmed preview to watched values. A new camera lease contains no frame or vector data.

Both GTK windows passed a private-display smoke test through enrollment, open, mark, close, report, export and student verification. This does not exercise physical camera drivers, real Redis, an actual phone scanner or another operating system. Copying a receipt transfers the ability to demonstrate inclusion. Administrative review and private receipt delivery depend on the teacher.
