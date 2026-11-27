# Decisions

- Use 0.80 as a provisional inclusive minimum on the mean winning-class softmax output of the two FasNet models. Only the real class qualifies. The installed source uses OpenCV, NumPy, torch and DeepFace, whose downloader imports gdown. Its transforms are local classes.
- Require a valid verdict for every returned candidate after exactly one candidate meets the existing geometry and confidence filters. A regression test covers a missing verdict on a small candidate. Detection, crop representation, cosine math, threshold, template cap and verification lockout parameters remain as live-verified.
- Group attendance by the calendar date in ZKAUTH_TIMEZONE. Use the system local timezone by default and Asia/Kolkata if it cannot be determined. An invalid explicit setting fails the operation. Store UTC ISO timestamps and render the original event in UTC and local time, including its offset, on marks, duplicate marks and reports. HSETNX inside the watched identification transaction deduplicates attendance across processes. Reports default to local today and create new export files exclusively.
- Keep the 60-second lockout for the winning ID during identification. Searching past that winner could credit another person.
- Cache models through DeepFace 0.0.93's own task/name registry. Warm long-running commands before capture. Default to physical cores and one inter-op thread.
- Report EER at the sampled threshold with the smallest absolute FAR/FRR gap, averaging both error rates. Report no EER without both kinds of pairs.
- Doctor uses the same active-key selection and validation as matching. Use module commands from the repository root. The snapshot audit treats inaccessible directories as incomplete evidence and returns FAIL.
- Preserve existing installations. Bind a new database to its first enrollment key. For legacy data without a fingerprint, authenticate every existing matrix before binding, under revision watch.
- Reuse the current venv. No dependency installation, model download, Redis access or live capture formed part of offline verification.

## Quality review decisions

- Make key provisioning the operator's responsibility. Writing a fresh key to disk contradicted the privacy boundary. Read existing v1 ciphertext and existing external keys as before. Rotation accepts only a different 32-byte key retained in advance. A disposable evaluation shell can keep an ephemeral key entirely in its environment.
- Validate the authenticated matrix's numerical contract before use. Each row must have squared norm within relative tolerance 0.0001 of one. This allows float32 normalization error. Require a positive threshold. Keep Facenet512, RetinaFace, the inclusive 0.70 match default and provisional 0.80 liveness default.
- Use the existing gallery revision to detect stale one-to-many searches. An exact tie between different users returns unknown. Multiple equally good templates of the same user still count for that user. A nonzero ambiguity margin needs independent comparison data.
- On the pinned redis-py 5.2.1 client, retry verification or identification at most eight times and only after the explicit watched-variable conflict. A lost acknowledgement can mean that a commit already happened. Report uncertainty and let the operator reconcile. Watching the bounded log adds contention in return for detecting schema errors before related writes.
- Require the active key to delete a template through the CLI. Redis authentication and access control remain the boundary against direct database writes. Preserve historical attendance.
- Restrict inference to local detector configurations supported by the inventory. Check cached weight headers even when liveness is disabled. GStreamer inherits only the desktop session variables it needs. Suppress its raw diagnostics. The operator can diagnose the session separately with gst-inspect.
- Reject multiline, control-containing or overlength names at enrollment. Escape legacy labels on display and prefix formula-like CSV cells. Keep stored names, IDs and ciphertext intact. Use a fresh mode-0600 CSV.
- Return exit 2 for a one-shot unknown identity. Repeat only recoverable sample and lockout failures. Keep sample refusals separate from the five below-threshold attempts that trigger lockout.
- Wipe arrays synchronously and retain final collection at process exit. Python cyclic garbage collection does not erase native tensors; a full heap scan per buffer added work without strengthening the overwrite. No CPU latency improvement is claimed without hardware trials.
- Keep the existing local-day implementation. Fix the live test guide to use Asia/Kolkata for both attendance and date selection. Keep the zone consistent across clients and across the life of a daily report.

## Signed desktop sessions

- Use Fedora's installed GTK 4 through system Python, with a separate project-venv worker. Keep the standalone student verifier in one file using cryptography and optional Tk or GTK. Test portability per operating system before distributing installers.
- Use one lecture record and a watched mark transaction shared with existing identification, lockout and access logging. Store UTC instants and show local time. Preserve the existing daily ledger, matching policy and encrypted template format.
- Sign a versioned summary using a separately provisioned Ed25519 school identity. Derive receipt tokens using a domain-separated HMAC secret, fresh random per-mark salt and private row data. Publish only sorted commitments or their signed root. An unclosed claim can use the finalized public bulletin; a closed receipt also carries its own inclusion path.
- Keep appeals and receipt handoff under teacher control. A reviewed correction makes a linked signed revision. A student can verify a specific revision offline; the class publication channel establishes which one is current.
- Isolate synthetic demonstrations in process-local fakeredis with an explicitly public demo identity. Live and demo verification use distinct trust domains. Export files are private, exclusive creations. Retention requires a fresh preview and a checked transaction.
