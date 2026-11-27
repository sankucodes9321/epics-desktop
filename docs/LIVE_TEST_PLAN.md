# Ten hardware acceptance tests

These are operator tests for a Fedora graphical session with consented volunteers. None ran during the offline review. Use the default 0.70 cutoff, 0.80 liveness floor and the same camera for each comparison. Record the actual decision, exit code, lighting and subject count, including refusals.

## Isolated setup

Install the pinned CPU environment and provision weights as described in README.md. Have the redis:7.4-alpine Docker image available locally. Run the following from the repository. It opens a child shell with a fresh in-memory key and a database configuration that cannot connect until you set the port. Closing this shell discards the evaluation secrets. Use your existing weights; this exercise needs no production enrollments or persistent key.

```bash
cd ~/epics
source .venv/bin/activate
python -c 'import os,base64,secrets; e={k:v for k,v in os.environ.items() if not k.startswith(("REDIS_","ZKAUTH_"))}; e.update(ZKAUTH_KEY=base64.b64encode(os.urandom(32)).decode(),REDIS_PASSWORD=secrets.token_hex(24),REDIS_HOST="127.0.0.1",REDIS_PORT="0",REDIS_DB="0",ZKAUTH_TIMEZONE="Asia/Kolkata",ZKAUTH_FORCE_CPU="1",CUDA_VISIBLE_DEVICES="-1",DEEPFACE_BACKEND_ENGINE="tensorflow",CAPTURE_BACKEND="gst-pipewire",HISTFILE="/dev/null"); os.execve("/bin/bash",["bash","--noprofile","--norc","-i"],e)'
```

Inside that child shell, start an isolated Redis server on a randomly assigned loopback port. Docker administrators are trusted. Only the Redis password is forwarded into the container. The EXIT trap stops this specific disposable container.

```bash
lab=$(docker run --pull=never --rm -d --tmpfs /data -p 127.0.0.1::6379 -e REDIS_PASSWORD redis:7.4-alpine sh -c 'exec redis-server --save "" --appendonly no --requirepass "$REDIS_PASSWORD"') || exit 1
trap 'docker stop "$lab" >/dev/null' EXIT
binding=$(docker port "$lab" 6379/tcp) || exit 1
export REDIS_PORT="${binding##*:}"
```

Run the tests below in this same shell, in order. The first two establish prerequisites for the higher-risk rejection tests.

1. **Check the environment before capture.** Expect four recognized weight headers, a working Redis connection, a valid active key and exit 0. Investigate WARN rows for swap or a CUDA-enabled torch build. Missing or invalid weights require explicit prefetch before repeating the check.

   ```bash
   python -m scripts.prefetch_models --check
   python -m scripts.doctor
   python main.py list-users
   ```

   The user list must be empty. Stop if it contains any existing enrollment.

2. **Establish a genuine baseline.** With Alice centered, expect a successful demo and three template additions. Vary pose slightly. Genuine verification should exit 0 and report the score. Record a failure even if the score is close.

   ```bash
   python main.py demo --verbose
   for i in 1 2 3; do python main.py enroll trial-alice Alice || break; done
   python main.py list-users
   python main.py verify trial-alice --verbose
   ```

3. **Challenge liveness.** With Alice out of view, run the following pair for each of a phone still, a printed photo and a video replay. A live-system acceptance with liveness enabled is an important failure. A detector or blur rejection alone does not demonstrate FasNet effectiveness. The disabled comparison is only for this disposable gallery. Record the rejection stage.

   ```bash
   python main.py verify trial-alice
   python main.py verify trial-alice --no-antispoof
   python main.py logs
   ```

4. **Check impostor decisions and lockout.** First have Alice complete a genuine match to reset any prior comparison failures. Then have Bob attempt the same identity five times. Only completed below-threshold comparisons increment the counter. Expect five exit-2 rejections and then a locked error without another camera capture. During the 60-second lock have Alice try identification or attendance. Neither should authorize the locked winner.

   ```bash
   python main.py verify trial-alice
   # Switch to Bob.
   for i in 1 2 3 4 5; do python main.py verify trial-alice; echo "status=$?"; done
   python main.py verify trial-alice
   # Switch to Alice.
   python main.py attendance
   python main.py logs
   sleep 61
   python main.py verify trial-alice
   ```

5. **Observe disk activity during genuine verification.** Expect PASS only after successful verification with full directory coverage and no image header in a changed regular file. An unreadable directory gives incomplete evidence. Optional strace records open paths and modes. Inspect changes even on PASS.

   ```bash
   python -m scripts.audit_no_disk_writes --user-id trial-alice
   python -m scripts.audit_no_disk_writes --strace --user-id trial-alice
   ```

6. **Exercise key and Redis failure handling.** With Alice in view, the temporary wrong key must fail authentication. With an unused loopback port, the metadata command must fail promptly. A subsequent genuine verification must still work. No key is printed.

   ```bash
   python -c 'import os,base64,sys; os.environ["ZKAUTH_KEY"]=base64.b64encode(os.urandom(32)).decode(); os.execv(sys.executable,[sys.executable,"main.py","verify","trial-alice"])'
   REDIS_PORT=1 python main.py list-users
   python main.py verify trial-alice
   ```

7. **Check gates and identification.** Run identify with the camera empty, then with two well-lit, centered faces that both meet size and confidence requirements. Expect a gate error. With only Bob in frame, before enrolling him, expect unknown and exit 2 if his comparison is below cutoff. Then enroll Bob twice and run identify with Bob alone. Expect trial-bob. Repeat with Alice alone and expect trial-alice.

   ```bash
   python main.py identify --verbose
   python main.py identify --verbose
   python main.py identify; echo "status=$?"
   python main.py enroll trial-bob Bob
   python main.py enroll trial-bob Bob
   python main.py identify
   python main.py identify
   ```

8. **Check attendance in IST.** With Alice in view, expect marked, then already marked today with the same original UTC and local timestamps. The report and CSV should contain one Alice row for the selected local date and show a +05:30 offset. Repeat across actual IST midnight if feasible. The offline tests also cover 23:59, 00:01 and UTC midnight without changing the system clock.

   ```bash
   python main.py attendance
   python main.py attendance
   python main.py attendance-report
   python main.py attendance-report --date "$(TZ=Asia/Kolkata date +%F)" --csv "attendance-$(date +%s).csv"
   ```

9. **Interrupt both loops and reclaim the camera.** Press Ctrl+C during capture in each loop before running the next command. Expect exit 130, no child belonging to the interrupted command and a working subsequent capture. Compare processes to the pretest desktop if other applications use GStreamer.

   ```bash
   python main.py identify --loop --interval 2 --verbose
   echo "status=$?"
   python main.py attendance --loop --interval 2
   echo "status=$?"
   pgrep -a -u "$(id -u)" -x gst-launch-1.0
   python main.py demo
   ```

10. **Measure the CPU pipeline and calibration sample.** With a genuine subject in view, expect ten completed benchmark iterations, per-stage seconds and process peak RSS in KiB. Calibration should report 66 thresholds using same-user and different-user template pairs. Save numerical outputs under new filenames. Test duration is not inference latency.

    ```bash
    python -m scripts.benchmark -n 10
    stamp=$(date +%s)
    python -m scripts.calibrate_threshold --csv "calibration-$stamp.csv" --json "calibration-$stamp.json"
    ```

Exit the child shell after collecting the results. Reports contain identifying metadata. Keep them private and follow the participants' retention agreement.

## Desktop and independent verification

Follow the seven-step workflow in [the desktop guide](DESKTOP.md) first in synthetic mode and then in the isolated live environment with a separate school signing identity. On the actual laptop, cancel and resume a camera scan, restart the teacher worker after a committed mark, publish a signed revision, verify a genuine receipt on a second computer and reject an altered bulletin. Record the OS, verifier version and whether QR decoding used a phone or the offline decoder.
