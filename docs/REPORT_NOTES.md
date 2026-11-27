# Report notes

The target is Fedora x86-64 with Python 3.11 and CPU inference. Direct pins include DeepFace 0.0.93, TensorFlow 2.15.1, Keras 2.15.0, tf-keras 2.15.1, NumPy 1.26.4, OpenCV 4.10.0.84, torch 2.6.0, cryptography 44.0.3 and redis-py 5.2.1. Offline tests use pytest 8.3.5 and fakeredis 2.28.1. Freeze the working installation for transitive versions.

RetinaFace localizes the face. Facenet512 retains compatibility with the enrolled 512-dimensional representation. Normalizing vectors allows a matrix product to score cosine similarity. The inclusive 0.70 cutoff preserves existing decisions. AES-256-GCM supplies confidentiality and integrity for templates at rest. Application decryption occurs only in RAM. Missing liveness evidence rejects the sample. A CPU wheel avoids pulling CUDA dependencies for a machine without a dedicated GPU.

Run the commands in LIVE_TEST_PLAN.md. Record subject count, number of sessions and attempts, camera and lighting, physical CPU cores, cold-start versus warmed latency, peak RSS, quality and liveness refusals, and genuine and impostor decisions. Use consented independent sessions for held-out evaluation. The calibration script enumerates distinct stored-template pairs at 66 thresholds. Its FAR, FRR and approximate EER describe that sample. Pair scores share templates and enrollment already filters low-similarity samples. These rates do not establish population accuracy or attack resistance. Report separate live spoof outcomes and sample counts. No live measurements are claimed here.

## Evidence levels

| Evidence | What can be reported |
|---|---|
| Operator's previous live observations | The original PipeWire capture, RetinaFace filter, Facenet512 embeddings, encrypted Redis storage, 0.70 matching, five-template cap, verification lockout, access log and core CLI worked on this laptop. |
| Real local code with synthetic inputs | NumPy cosine scoring, AES-GCM authentication and failure cleanup, export permissions, time conversion, calibration arithmetic and on-disk audit header detection ran offline. |
| Test doubles | Model responses, missing weights, camera errors, framework thread settings, Redis transactions, clock boundaries, interrupted loops and doctor failure paths. Fakeredis models Redis operations in memory. |
| Still to measure | Genuine and presentation rejection rates, errors under actual lighting, CPU latency and RSS, real Redis concurrency and disconnects, PipeWire cleanup after interrupts, download reliability and container integration. |

There are no timing or accuracy claims based on the unit test runtime. Report quality and liveness refusals alongside completed comparisons so the denominator is visible. A snapshot PASS is limited to its listed directories and observation window.

Benchmark stages can overlap (capture can include scratch wiping). Peak RSS covers the process lifetime, including warm-up. The benchmark exercises comparison and encryption without issuing a user access decision or updating lockout.

## Distinctive contribution

The system combines a probabilistic identity decision with independently verifiable inclusion in one finalized lecture register. The teacher can display a signed QR. A student can verify a bearer receipt against an anonymous bulletin on another computer using the school's trusted Ed25519 public key. No class list or biometric dependency is required on the verifier. A correction creates a new signed revision. Publish the intended revision through the class channel.

For a viva, demonstrate a duplicate scan, verify a receipt issued before closure, then alter a copy of the anonymous bulletin and repeat verification. Discuss the two different questions being answered: the live camera trials measure recognition and liveness; the receipt test establishes mathematical inclusion in one signed version. The numerical unit test count is evidence about software behavior only.
