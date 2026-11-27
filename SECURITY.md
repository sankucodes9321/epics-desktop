# Threat model

This application handles biometric data on a trusted Linux workstation. It aims to limit disclosure through ordinary application output, abandoned capture buffers and theft of a Redis snapshot. The host, camera stack, installed dependencies, model weights and local operator must be trusted.

## Protections

- The application processes frames and crops in memory. It does not encode, upload, log or save them. Model provisioning downloads weights. Redis receives ciphertext, identity metadata and access decisions.
- AES-256-GCM protects the template matrix at rest and authenticates the user ID, model, dimension and count as associated data. Supply keys from a trusted secret manager or an existing external mode-0600 file. Protect backups separately. Application commands never create key files. Names, IDs, timestamps, counts, scores and outcomes are visible to Redis readers.
- Capture, quality scratch arrays, returned crops, embedding arrays and decrypted template storage are overwritten on their cleanup paths. The CLI disables core dumps, attempts memory locking on sensitive contiguous buffers, and requests final garbage collection at normal interpreter shutdown.
- Verification locks a user ID for 60 seconds after five consecutive below-threshold comparisons. Identification and attendance recheck lockout on the winning ID before committing a decision. Quality failures and spoof rejections do not count as below-threshold matches.
- Exactly one qualifying face, a real-face verdict by default and quality gates reduce accidental matches and simple presentation attacks. Redis access events have bounded retention. Restrict access to these identifying logs.

## Limits and host controls

Python, TensorFlow, PyTorch, drivers and the kernel can retain internal copies of frames, embeddings and keys. Best-effort memory locking is subject to OS limits and cannot cover every copy. A crash or forced termination can bypass cleanup. Swap, hibernation and host-level crash collectors can persist sensitive RAM.

Disable disk-backed swap or encrypt it. Check active swap with `swapon --show` and distinguish RAM-backed zram from disk-backed devices. Disable hibernation and hybrid sleep through the host power policy. Use full-disk encryption for the OS, Redis volume, key files and backups. Review host crash collection separately, including piped core handlers. Verify these policies after reboot.

A compromised host or operator with the key and ciphertext can decrypt templates. Embeddings can disclose information about a person and support linkage across records. Authentication does not prevent deletion, rollback of Redis data, tampering with unauthenticated metadata, or denial of service. The Redis password controls access but does not encrypt transport. Keep the deployment local.

Single-frame anti-spoofing can accept sophisticated attacks and reject real people. Lighting, focus, camera geometry and subjects affect performance. The testing override removes the liveness check. This system alone does not establish identity for high-assurance access.

Attendance hashes contain the ID, display name, UTC timestamp and score in plaintext. Daily hashes persist until removed under the operator's retention policy. Reports omit scores. A testing override adds antispoof=off to applicable access events. The 0.80 liveness floor is provisional. Trust the source of all prefetched weights. The pinned source provides no cryptographic digest for these four downloads.

## Operational boundaries

A valid GCM tag proves possession of the correct key at encryption time. After authentication the reader also checks the normalized-vector contract; failures wipe the decryption destination. The user ID, model and count are bound to the ciphertext. Display names, access events, attendance and the gallery revision are trusted Redis metadata. An operator with unrestricted Redis credentials can alter them or bypass CLI deletion checks. The access log is a bounded diagnostic stream, not tamper-evident evidence.

The GStreamer subprocess receives a limited session environment and has no diagnostic file configured by the app. The Python process, model packages, model cache, working directory and OS remain trusted. Model header checks detect some bad downloads. They do not authenticate the publisher or validate every byte. Explicit prefetch is the supported download path. A trusted cache must remain stable during inference. Environment keys can be observed by sufficiently privileged local processes.

Redis MULTI/EXEC serializes commands and WATCH detects conflicting writers. Redis does not roll back individual command failures. The app checks relevant key types, revision and counters before sensitive writes. An interrupted connection can leave commit status unknown. Stop writers and reconcile using metadata and logs before repeating a mutation. Restrict direct database access and maintain tested backups. Lockout is per claimed identity for below-threshold verification; unknown identification attempts have no global rate limit.

CSV reports contain personal data and are created with mode 0600. The CLI escapes terminal controls and guards formula-like cells. Protect copied reports and choose your own retention period. A disk snapshot inspects headers of surviving new or changed files only. Transient files, framework copies, swap and network traffic need separate evidence.

## Signed class sessions

The teacher's Ed25519 seed is separate from the AES enrollment key. The verifier trusts a school public key obtained through an independent channel. Private receipts contain bearer tokens. A public bulletin reveals a course label, count, time, revision, commitments and changes across versions. Do not include names in course labels. A Merkle proof establishes inclusion of a commitment in a signed revision. It cannot establish personal possession of the receipt, continuous physical presence, completeness before signing or which revision is latest. The teacher, operating system and Redis remain trusted. Redis rollback, lost signing seeds, a compromised teacher and redistribution of private receipts require operational controls. Demo signatures are deliberately reproducible and rejected by live verification.
