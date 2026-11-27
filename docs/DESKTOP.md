# Signed classroom attendance

## Run a two-minute demonstration

Use a Fedora graphical session. The system interpreter needs PyGObject, GTK 4, its Cairo bridge and cryptography. The teacher's worker uses the existing .venv. Public QR display uses libqrencode.so.4 from qrencode-libs. To provision an additional Fedora workstation, the relevant desktop packages are gtk4, python3-gobject, python3-cairo, python3-cryptography and qrencode-libs. Run `make setup-demo` for synthetic classes or `make setup` for live camera recognition.

1. From ~/epics run `/usr/bin/python3 teacher_app.py --demo`. The window is labeled **Synthetic demo**. Its Redis database, sample vectors and enrollment key are local to this worker. Closing the app discards the demo database.
2. In **Enrollment**, enter ID `demo-student`, choose a name and click **Enroll sample**. In **Live class**, enter a course, section and lecture label, then click **Open class**. Leave the simulated student ID as `demo-student`.
3. Click **Mark once** twice. Expect marked, then already marked. Try another, unenrolled simulated ID and expect unknown. A second lecture can count the same student independently.
4. In **Publication**, enter the enrolled ID and export the student's private receipt to a fresh filename. This works before finalization. Hand it to the intended student privately. For recovery, the teacher can re-export a current student's claim from the same retained session.
5. In **Register**, view the roster and finalize the selected session. Return to **Publication** and export the public register. The public QR displays the signed summary. The exported public register also includes the anonymous commitments needed to check a claim issued before closure.
6. Open `/usr/bin/python3 student_verifier.py --demo` and select the public register and receipt. The result identifies the lecture, revision and demo domain. On a second laptop, copy only student_verifier.py and the two documents. The CLI needs Python and cryptography. Use a Python interpreter with Tk for the GUI, or GTK 4 on Fedora.
7. On a disposable copy of the public register, remove a commitment or change the signed count and try again. Expect verification failure. A successful receipt proves inclusion in the specified revision. It gives no duration-of-attendance or biometric-accuracy guarantee.

Example command for an independent machine with Python and cryptography:

```bash
python student_verifier.py --demo --summary public-register.json --receipt private-receipt.json
```

## Live setup

### This GNOME installation

Open **EPICS Attendance** from Activities for the live teacher workspace. **EPICS Student Verifier** checks live receipts independently. **EPICS Attendance Demo** opens the synthetic workspace.

The live teacher launcher retrieves this installation's signing seed from the GNOME login keyring. Both live launchers read the trusted public key from `~/.config/epics-attendance/school-public-key`. Students using another computer can enter that public key in their verifier after receiving it through a trusted channel. Retain the signing identity in your school's secret backup before moving to another teacher account or machine.

### Other installations

Use your existing gallery key, Redis endpoint, protected model cache and CPU environment. The live teacher requires liveness enabled and a matching school signing identity. Have the school's secret manager provision an Ed25519 identity, retain its secret and make its public key independently available to students.

| Value | Where it belongs |
|---|---|
| ZKAUTH_SIGNING_SEED | Teacher environment only. Standard base64 encoding of the raw 32-byte Ed25519 seed. Use a different secret from the AES template key. Keep it available across restarts for receipt recovery and revisions. |
| ZKAUTH_SCHOOL_PUBLIC_KEY | Standard base64 encoding of the corresponding raw 32-byte public key. Supply to the teacher and distribute independently to students. A verifier must never take its trust anchor from the receipt or QR. |
| ZKAUTH_TIMEZONE | Set Asia/Kolkata for a consistent IST roster. Session identity is per lecture. Daily attendance via the original CLI still uses local calendar days. |

Start `/usr/bin/python3 teacher_app.py`, run **System check**, and address FAIL rows before enrollment. **Start scanning** repeats until cancelled or an operational failure. The camera and models run outside GTK. A per-user lock serializes captures from this application's processes. A lock file contains no data. Cancellation first interrupts the worker. If native code remains blocked after four seconds, the app terminates its process group. After worker loss, use **Restart worker**, then view the register before retrying an interrupted action. After an uncertain commit, refresh and review the register. A committed mark remains recoverable in Redis. Restarting a synthetic worker starts a new demonstration.

The GUI honors desktop text scaling and native keyboard focus. `--hindi` translates teacher navigation and primary control labels. Diagnostic messages, trial categories and some status values remain English. No viewer needs the AES key, signing seed, enrollment roster, camera, models or a network connection.

## Register, appeals and retention

**Register** shows the attendance count, names, IDs and both UTC and local times. Use the search field to filter the displayed roster by student name or ID. For a missed scan or disputed entry, the teacher receives the appeal privately, views the current revision, expands **Correction**, enters the relevant ID and a private review reason, then chooses include, remove or uphold. Confirm the signed revision. Manual inclusion requires an enrolled ID. Uphold records the review while preserving the roster. After signing, the workspace loads the updated register and reviewed revision. Publish the revised summary and distribute updated proofs as needed.

Every revision links to its predecessor's signed document. Old proofs still verify for their original revision. Students should obtain the intended revision through the class publication channel. An isolated verifier cannot discover a later revision. The public QR contains the course label, so keep identifying student information out of that label. Receipts are transferable bearer documents; use individual, private delivery. The teacher OS account is the administrative trust boundary. Keep enrollment, the shared teacher screen and the school's secret manager under operator control.

**Retention** previews the exact Redis keys for daily attendance before a local cutoff and closed sessions whose latest revision predates it. Confirmation deletes only the previewed, unchanged records, including their private roster, corrections and server-side recovery material. Open sessions and encrypted gallery templates remain. Published files and copies already held by students persist. Review the preview before confirming.

## Evaluation

Enroll at least two test users to measure the gap between the top two distinct identity scores. For a genuine trial enter the expected enrolled ID. For an impostor identification trial use an unenrolled volunteer. Phone photo, printed photo and video replay are separate trial categories. Only count an actual liveness rejection as evidence about FasNet. A scored unknown identity counts as a correct impostor identification. For a photo or replay, a face that passes liveness counts as a failed liveness trial even if its identity is unknown. Rejections without a usable outcome and synthetic presentation trials are recorded as inconclusive.

Export aggregate results before closing the teacher worker. The JSON groups trials by scenario, including counts, correct and inconclusive outcomes, reasons, elapsed time and the mean score gap where available. No names or sample vectors go into the evaluation file. Live trial latency can include model initialization on first use. Use the benchmark script for warmed stage timings.

## Session CLI

From the activated project venv in a live configured deployment:

```bash
python -m scripts.classroom open "CSE A, Algorithms, lecture 4"
python -m scripts.classroom list
python -m scripts.classroom mark SESSION_ID
python -m scripts.classroom report SESSION_ID
python -m scripts.classroom close SESSION_ID
python -m scripts.classroom receipt SESSION_ID STUDENT_ID private-receipt.json
python -m scripts.classroom publish SESSION_ID public-register.json
```

Use the ID returned by open. Close is idempotent. Exports require fresh filenames. Sessions use Redis keys under zkauth:session:v1: and support up to 1,000 current marks per lecture. This design reads and rewrites a lecture record under WATCH and is intended for a class. Deployment at campus scale would need performance and contention testing.

## Platform and validation

The teacher targets Fedora Linux. It depends on the system GTK environment, PipeWire, Linux file locking and the local CPU runtime. The student verifier CLI and Tk interface avoid Linux APIs and have no imports from the teacher package. Windows and macOS are portability targets for the verifier. Native installers and platform acceptance tests for those systems have not been produced.

Run the offline suite with `.venv/bin/python -m pytest -q`. Fedora's optional native smoke test runs with `/usr/bin/python3 tests/gtk_smoke.py` and requires gtk4-broadwayd with permission to create private Unix display sockets. It opens both GTK windows on an isolated display and exercises enrollment, marking, closure and reporting using synthetic data. For real hardware follow LIVE_TEST_PLAN.md and repeat the desktop demo in a dedicated evaluation database using independently provisioned live keys. Verify camera cancellation during model inference, persistence across a worker restart, two-client mark versus close contention, QR readability with a phone, receipt delivery and independent verification on the intended second laptop.
