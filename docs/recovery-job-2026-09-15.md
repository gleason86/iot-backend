# Recovery-job validation coverage and MQTT-stage diagnosis — 2026-09-15 UTC

## Lock corrected, 2026-09-16 06:55 UTC

The O_EXCL-plus-stale-age lock described below was unsafe (live-owner theft
after 30 minutes, PID-guess takeover, unlink-by-pathname release). Replaced by
an OS-held exclusive lock (`msvcrt.locking` / `fcntl.flock`) held for the run;
metadata informational only; release closes this descriptor only; abnormal
exit recovers because the OS drops the lock. Tests: `tests/test_recovery_lock.py`
(5, real subprocess contention) and adapted `tests/test_daily_recovery.py`;
115 tests in discovery and in the container. Scheduled 10:15 UTC result pending.

Worker: recovery-code worker for `iot-backend`, reporting to lead
`claude-fable-monitor-lead-20260915` (holds claims; `~/.agents/tools/coordinate.py`
not used by this worker). Scope: (C1) wire the existing unit tests into the
disposable container validation path; (C2) read-only diagnosis of why the daily
recovery job's MQTT stage has failed three times today, plus a tested (not
applied) fix for the job's failure semantics. No schedule change, no MQTT
export change, no real run of `daily-recovery.py`/`influx-recovery.py`/
`mqtt-recovery.py`/`encrypt-checkpoint.py`, and no git state changes were made.

## C1 — container validation now runs every unit test

Before this change, `tests/validate.sh` discovered only `test_monitor.py` and
`tests/Dockerfile` did not copy `tools/`, so `tests/test_provision_infra.py`,
`tests/test_encrypt_checkpoint.py` and `tests/test_verify_credential_restore.py`
never ran in the routine container check, even though all three are fully
mocked and safe to run with no network and no host access.

**Changes:**
- `tests/validate.sh`: discovery pattern widened from `test_monitor.py` to
  `test_*.py`. `integration_provision_infra.py` and `*_drill.py` need real
  Docker/host resources and are deliberately **not** matched by this pattern
  (unittest's `test_*.py` glob only matches files starting with `test_`), so
  they stay out of the disposable run without any extra exclusion logic.
- `tests/Dockerfile`: added `COPY tools tools` so `tools/provision_infra.py`
  (imported by `tests/test_provision_infra.py` and by
  `scripts/verify-credential-restore.py`, which `tests/test_verify_credential_restore.py`
  loads) is present in the image. `.dockerignore` already excludes
  `secrets`, `.env`, `data`, `mosquitto/password.txt` and `**/__pycache__`,
  so nothing sensitive or stale entered the build context.
- New `tests/test_daily_recovery.py` (see C2) is picked up by the same
  widened pattern with no further wiring needed.

All four affected test files were read in full: every one mocks
`subprocess`/`docker` calls (or, for `test_monitor.py`, calls pure functions)
and writes only to per-test temp directories — none opens a live Docker
socket, a host disk path outside its own temp dir, or the LAN.

**Build/run, exactly as documented in `threadripper/docs/completion-progress-2026-09-11.md`:**

```
docker build -t iot-recovery-validation -f tests/Dockerfile .
docker run --rm --network none iot-recovery-validation
```

**Result:** build succeeded (base `threadripper-validation`, already local).
Container run (`--network none`, no volumes, no `-v /var/run/docker.sock`,
no credentials) passed everything:

- `python -m py_compile` on `influx-recovery.py`, `encrypt-checkpoint.py`,
  `restore-standby.py` — clean.
- `python -m unittest discover -s tests -p 'test_*.py'` — **80 tests, all
  passing** (9 `test_daily_recovery`, 6 `test_encrypt_checkpoint`, 2
  `test_monitor`, 55 `test_provision_infra`, 8 `test_verify_credential_restore`).
- `ansible-playbook tests/standby.yml -i localhost, --syntax-check` — passed.
- `ansible-playbook playbooks/restore-checkpoint.yml -i threadripper, --syntax-check` — passed.
- `ansible-playbook tests/render.yml -i localhost,` — passed (template render).

Nothing needed isolating beyond what the test authors had already mocked;
no test file required changes to make it container-safe.

## C2 — daily job MQTT-stage failure

### Facts gathered (all read-only)

- `Get-ScheduledTaskInfo -TaskName 'IoT Backend Verified Encrypted Recovery'`:
  `LastRunTime = 2026-09-15 03:15:01 (Pacific)` = 10:15 UTC, `LastTaskResult = 1`
  (generic failure exit code), matching the scheduled run named in the brief.
- `docker ps -a`: **`iot-mosquitto` is `Exited (255)`**, not restart-looping.
  `docker inspect iot-mosquitto` `.State`: `StartedAt 2026-09-09T16:18:55Z`,
  **`FinishedAt 2026-09-15T05:07:26Z`, `ExitCode 255`, `OOMKilled: false`**.
  `docker logs -t iot-mosquitto` ends mid-cycle at `2026-09-15T04:53:03Z`
  ("Saving in-memory database…") with **no clean-shutdown log line** ("...
  terminating" is mosquitto's normal SIGTERM message and never appears) —
  consistent with the container being killed externally or the daemon
  restarting while it happened to be stopped, not a graceful stop.
- `docker-compose.yml`: mosquitto's `restart: unless-stopped` should bring it
  back automatically after a crash; its current `exited` (not `restarting`)
  status indicates Docker considers it *deliberately* stopped, not
  crash-looping — i.e., something explicitly stopped/killed it rather than it
  repeatedly failing to start.
- `iot-telegraf` is separately restart-looping (`RestartCount` in four
  figures, latest error `dial tcp: lookup mosquitto on 127.0.0.11:53: no such
  host`) — this is the **pre-existing, already-flagged** issue from
  `docs/infra-monitoring-2026-09-15.md` and is a *symptom* of mosquitto being
  down (Docker's embedded DNS only resolves a service name while that
  container is running), not a separate root cause.
- `data/` staging listing (names/sizes only): three undeleted
  `daily-2026...` directories (`20260915T101502Z`, `20260915T234120Z`,
  `20260915T234235Z`) plus the two `monitoring-*` and `recovery-2026091*`
  directories from other tasks — consistent with the brief's report that all
  three runs got past the Influx/encrypt/tar/off-host-copy stages and left
  their decrypted staging behind. No `mqtt-20260915T*` directories exist
  under `data/`, confirming `mqtt-recovery.py` never reached the point where
  it creates its own output directory.
- **No secrets/`.env`/`mosquitto/password.txt`/`D:\Backups` archive contents
  were read.** Only `docker ps`/`inspect`/`logs`, `Get-ScheduledTask*`, and
  `data/` directory listings were used.

### Root cause hypothesis

`mqtt-recovery.py`'s very first live action is
`r.command(['docker', 'kill', '--signal', 'SIGUSR1', 'iot-mosquitto'])`
(line 24). Since `iot-mosquitto` has been in `Exited` state since
**2026-09-15T05:07:26Z** — well before the 10:15 UTC scheduled run and both
23:41/23:42 UTC manual runs — `docker kill` against a non-running container
fails immediately (`Cannot kill container: … is not running`), `command()`
raises its private `RuntimeError`, and the whole script exits non-zero before
doing anything else. `daily-recovery.py`'s own `cmd()` wrapper around the
`mqtt-recovery.py` invocation (previously line 53) then raises, aborting the
job at the MQTT stage — after the Influx backup, encryption, tar and verified
off-host copy have already succeeded, and before `latest.json` is written or
staging is cleaned up. This matches all three observed failures with a single
cause: **the MQTT stage fails because the broker container it targets is not
running**, not because of anything specific to the recovery script's logic.
Restarting `iot-mosquitto` was out of scope for this read-only task and was
not done.

## Fix implemented in `scripts/daily-recovery.py` (tested, not scheduled/run)

- **Per-stage tracking** for `influx_backup`, `encrypt`, `tar`, `offhost_copy`,
  `mqtt_export`, `mqtt_copy`, written to `D:/Backups/iot-backend/status.json`
  (`{observed_at, overall, stages: {...}, failing_stage?}`) on every exit path,
  and mirrored into the run's report (`latest.json`/stdout) via the same
  `stages` field.
- **`latest.json` semantics:** on full success, `overall: "success"` with both
  Influx and MQTT fields. If `mqtt_export` or `mqtt_copy` fails, `latest.json`
  is still updated with the already-verified Influx fields
  (`archive`, `independent_copy`, `sha256`, `native_restore_verified`,
  `encrypted_restore_verified`), plus `overall: "partial"` (never `"success"`)
  and `failing_stage`. If an earlier stage fails (`influx_backup`, `encrypt`,
  `tar`, `offhost_copy`), `latest.json` is left **completely untouched** —
  verified by a test that seeds a sentinel `latest.json` and asserts its bytes
  are unchanged after a simulated `influx_backup` failure.
- **Bounded cleanup:** the decrypted staging directory (`data/daily-<stamp>`)
  is now removed immediately once `offhost_copy` succeeds — independent of
  the MQTT stage — using the exact same path-containment guard
  (`resolved.parent == ROOT/'data'` and `resolved.name == 'daily-'+stamp`)
  as before, just moved earlier in the pipeline instead of at the very end.
  A retention cap for leftover staging directories was left out of scope (not
  trivial to bound safely without a policy decision on how many
  known-undeletable runs to keep).
- **Sanitized failure evidence:** `StageFailure(stage, exit_code, tail)`
  carries the failing stage name, the subprocess exit code, and a
  redacted/truncated (last 20 lines) stderr tail. Redaction
  (`redact()`) removes (a) any value following `token`, `password` or
  `Authorization` (case-insensitive, optionally through a `Bearer` prefix),
  and (b) any 32+ character base64/hex-shaped run, even without a keyword.
  Successful stages are unaffected — `cmd()`'s existing behavior of never
  surfacing subprocess stdout is unchanged.

## Tests — `tests/test_daily_recovery.py` (new, 9 tests, all passing)

`subprocess.run` is fully mocked (a fake dispatcher recognizes each real
command by its argv shape and performs only the minimal filesystem side
effect `main()` depends on); `ROOT`/`DEST` are patched to per-test temp
directories, `shutil.disk_usage` is patched, and `datetime.now` is frozen so
stamps/paths are deterministic. No real Docker, SSH, scp or host disk state
is touched.

- **All-success path:** every stage `ok`, `latest.json` `overall: "success"`
  with both Influx and MQTT fields, staging removed, status.json mirrors the
  printed report.
- **MQTT failure path** (both `mqtt_export` and a separate `mqtt_copy`
  variant): `latest.json` `overall: "partial"` with the correct
  `failing_stage`, Influx fields present, MQTT fields absent, staging
  **removed** (off-host Influx copy already verified), later MQTT sub-stage
  left `pending`, and a fixture secret embedded in the fake stderr does not
  appear in `status.json`'s stored tail.
- **Influx-side failure paths:** an `influx_backup` failure leaves a
  pre-seeded `latest.json` byte-for-byte unchanged and leaves all later
  stages `pending`; a later `offhost_copy` failure leaves the staging
  directory **retained** (with its `verification.json` still present) for
  diagnosis, since cleanup only happens once that stage itself succeeds.
- **Redaction:** direct tests of `redact()` for keyword-prefixed values,
  long bare hex/base64 runs, and that short/ordinary text is left alone; a
  `StageFailure` construction test confirms its `.tail` is both redacted and
  capped at 20 lines.

## Command the lead would run to exercise the fixed job (once approved)

Not run by this worker. Once `iot-mosquitto` is confirmed healthy again
(`docker start iot-mosquitto` or a full `docker compose up -d`, which is
outside this task's read-only/no-run boundary), the lead can exercise the
fixed pipeline exactly as the schedule does:

```
python scripts/daily-recovery.py
```

Expected with the fix, if `iot-mosquitto` is healthy: `overall: "success"` in
both `status.json` and `latest.json`, all six stages `ok`. If MQTT is still
unhealthy for any reason: the run now leaves `latest.json` at
`overall: "partial"` with `failing_stage: "mqtt_export"` and the current
Influx checkpoint fields (instead of a stale `2026-09-14` `latest.json` and a
bare traceback), and the three existing orphaned staging directories under
`data/daily-2026091*` are unaffected by this run (only the run's *own* new
staging directory is subject to the new earlier cleanup) — those three remain
the cleanup candidates already tracked in
[Threadripper's audit](../../threadripper/docs/monitoring-recovery-2026-09-15.md#cleanup-candidates-need-the-users-go-nothing-deleted)
pending the user's go-ahead.

## 2026-09-16 — full stage/status coverage, split checkpoint files, lock, atomic writes

Worker: bounded implementation worker for `iot-backend`. Lead:
`claude-fable-monitor-closeout-20260916` (holds claims; `coordinate.py` not
used). Scope: close the gaps the lead's closeout prompt identified in the
2026-09-15 fix above — capacity checks, archive hashing, staging cleanup and
MQTT result validation were still outside stage/status handling, report
writes were non-atomic, and a report-write failure or unexpected exception
could still print a raw traceback. No schedule change, no MQTT export
change, no real run of `daily-recovery.py`/`influx-recovery.py`/
`mqtt-recovery.py`/`encrypt-checkpoint.py`, and no git state changes were
made. Owned paths only: `scripts/daily-recovery.py`,
`tests/test_daily_recovery.py`, this section.

### Facts checked before editing (all read-only)

- `schtasks /query /tn "IoT Backend Verified Encrypted Recovery" /fo LIST /v`:
  **Next Run Time 9/16/2026 3:15:00 AM**, **Last Run Time 9/15/2026 3:15:01
  AM**, **Last Result 1** (the known MQTT-stage failure), multiple-instances
  policy is Task Scheduler's `IgnoreNew` (`install-recovery-task.ps1`'s
  `-MultipleInstances IgnoreNew`) plus a 20-minute execution time limit — the
  schedule itself already refuses a scheduler-triggered overlap, but a manual
  `python scripts/daily-recovery.py` run has no such protection, which is
  what the new in-script lock now covers.
- `Get-CimInstance Win32_Process -Filter "Name like 'python%'"`: no process
  running `daily-recovery.py`, `influx-recovery.py`, `mqtt-recovery.py` or
  `encrypt-checkpoint.py` at the time of editing (only unrelated `grafana`
  MCP and `trmnl` news-model processes were running). Editing proceeded.
- Consumers of `D:\Backups\iot-backend\latest.json`/`status.json`: grepped
  `iot-backend`, `threadripper` and `grafana` for both filenames. No
  programmatic consumer exists anywhere in the three repos — every hit is
  prose in dated docs (this repo's own docs, `threadripper/docs/monitoring-
  recovery-2026-09-15.md`, `service-continuity-2026-09-11.md`,
  `completion-progress-2026-09-11.md`) or unrelated: `threadripper`'s
  `dependencies.json`/`test_monitoring_health.py` "status.json" hits are
  `terminus-health`'s own receipt file (a different host, different job);
  `grafana/tools/recovery_checkpoint.py` writes its *own* independent
  `latest.json` for a different backup root; the Grafana topology dashboard's
  Flux query computes unrelated in-memory health-status codes. Nothing reads
  or parses `D:\Backups\iot-backend\latest.json`/`status.json` today, so this
  change is free to split their meaning without breaking a reader.

### Design decision: `latest.json` vs `latest-influx.json`

Given no consumer was found, `latest.json` now means exactly one thing: the
entire pipeline, through the final MQTT copy and staging cleanup, fully
succeeded. It is written once, atomically, only at the very end of a
completely clean run. A brand-new `latest-influx.json` is written
immediately after the off-host Influx copy's checksum is independently
verified — before staging cleanup and before any MQTT work — and always
reflects the newest verified Influx checkpoint regardless of what happens
afterward. A consumer can therefore no longer mistake a stale `latest.json`'s
`completed_at` for "today succeeded": if `latest.json` is stale/absent but
`latest-influx.json` is fresh and `status.json`'s `overall` is `"partial"`,
that truthfully means the Influx side is current but something later (MQTT,
or cleanup) did not complete.

### What changed in `scripts/daily-recovery.py`

- **`STAGES` grew from six to eight**: `preflight` (capacity/free-space
  checks, previously unhandled `OSError`s before any stage existed) and
  `cleanup` (previously an unconditional call with no status entry) are now
  first-class stages with their own try/except and status entry.
- **Archive hashing** (the main Influx `encrypted.tar`) moved inside the
  `offhost_copy` try block, so a missing/unreadable archive at hash time is a
  recorded `offhost_copy` failure instead of an unhandled traceback.
- **MQTT result validation** (`mqtt_export` stage): the subprocess stdout is
  parsed as JSON, the `archive` key is checked for presence/type, and the
  path is validated against the *shape* of `mqtt-recovery.py`'s own output
  directory (`DEST/mqtt-<UTC timestamp>/encrypted.tar`) rather than an exact
  expected path — `mqtt-recovery.py` generates its own timestamp independent
  of `daily-recovery.py`'s, so the exact directory name can't be known ahead
  of time, only its shape and containment under `DEST`. The file is also
  opened for one byte to catch "exists but unreadable" (tested with a
  directory standing in for a file, portable across platforms). All four
  malformed-response cases (non-JSON, missing key, path outside `DEST`,
  unreadable) are attributed to `mqtt_export`, never expose `stderr_tail`.
- **Cleanup is now non-fatal and independent of MQTT**: a `remove_staging()`
  failure (e.g. `PermissionError`) is recorded against the new `cleanup`
  stage but does **not** raise — the already-written `latest-influx.json` is
  untouched, and the MQTT stages still run afterward. If everything else
  (including both MQTT stages) succeeds but cleanup failed, the run still
  reports `overall: "partial"` with `failing_stage: "cleanup"` and does
  **not** write `latest.json`, since cleanup failing means the run was not
  fully clean.
- **Controlled failure summaries, not regex scrubbing, as the primary
  control**: `TAIL_ALLOWED_STAGES = {tar, offhost_copy, cleanup, mqtt_copy}`.
  Only those four stages may carry a redacted `stderr_tail` in `status.json`;
  `preflight`, `influx_backup`, `encrypt` and `mqtt_export` (all of which
  invoke code that reads Influx/restic/MQTT tokens and passwords) get only a
  stage name, exit code and a fixed, allowlisted `description` string from
  `STAGE_DESCRIPTIONS`. `redact()`/`StageFailure.tail` are unchanged and kept
  as defense in depth on whatever tails are still allowed through.
- **`subprocess.TimeoutExpired` is now caught** in `cmd()` and converted into
  a `StageFailure(stage, 'timeout', ...)` instead of propagating a raw
  exception (which can carry partial captured stdout/stderr).
- **Atomic report writes**: `atomic_write_json()` writes a `.tmp-<pid>` file
  and `os.replace()`s it into place for `status.json`, `latest.json`,
  `latest-influx.json` and `lock-conflict.json`.
- **`cli_main()`** wraps `main()` (used only by the `if __name__ ==
  '__main__'` entry point, not by tests calling `main()` directly): a
  `LockHeld` is turned into a `lock-conflict.json` (never touching the
  in-progress run's own `status.json`) plus exit 1; any other unexpected
  exception — including a report-write failure itself, such as `os.replace`
  raising — is turned into a sanitized `{overall: "error", error: "<Type>:
  <redacted message>"}` written to `status.json` on a best-effort basis, with
  no raw traceback ever printed.
- **In-script exclusive lock**: `D:/Backups/iot-backend/daily-recovery.lock`,
  created with `os.O_CREAT | os.O_EXCL`. A held lock is treated as stale (and
  replaced) if its recorded PID is no longer alive (`OpenProcess` on Windows,
  `os.kill(pid, 0)` elsewhere) or if the lock file is older than 30 minutes
  (longer than the task's 20-minute execution time limit). A live,
  non-stale lock causes an immediate refusal before any stage runs, touching
  only `lock-conflict.json`.

### Tests — `tests/test_daily_recovery.py` (22 tests, all passing; was 9)

Every test now drives the script through the real `cli_main()` entry point
and asserts on the resulting exit code as well as file contents (previously
tests called `main()` directly and asserted on a raised exception). New
coverage: cleanup denial (`rmtree` → `PermissionError`, Influx evidence
survives, MQTT stages still run, final `overall: "partial"`), all four
malformed-MQTT-response variants, a missing Influx archive at hash time
(tar succeeds, then the file vanishes before hashing), a capacity/free-space
failure, a subprocess timeout with a fixture secret confirmed absent from
`status.json`, an atomic-write failure (`os.replace` mocked to fail only for
`latest.json`, confirming `latest-influx.json` survives and the summary is
sanitized with no `Traceback`/`File "..."` text anywhere in output), an
overlapping-run lock conflict (pre-seeded live lock, sentinel `status.json`
proven byte-identical afterward) and a stale-lock replacement (old PID/old
mtime, run proceeds to success), plus a direct unit test of the
`TAIL_ALLOWED_STAGES` gate in `mark_failed()`. All pre-existing scenarios
(all-success, both MQTT failure modes, Influx-backup/encrypt/offhost-copy
failures, the four `redact()`/`StageFailure` tests) were kept and updated for
the new file layout.

### Test/container results

- `python -m unittest tests.test_daily_recovery`: **22 passed** (was 9).
- `python -m unittest discover -s tests -p 'test_*.py'` on the host: 109
  tests total; two `test_verify_threadripper_checkpoint.py` failures were
  observed intermittently, unrelated to this change (that file is untracked,
  owned by a different concurrent worker, not touched here, and not
  reproducible inside the clean container — see below).
- Disposable container (`docker build -t iot-recovery-validation -f
  tests/Dockerfile .` then `docker run --rm --network none
  iot-recovery-validation`): **109 tests, all passing**, plus the existing
  Ansible syntax/render checks, with no network and no Docker socket mount.

### Not yet exercised live

The fixed job has **not yet been run for real** — this remains "not yet
exercised live", not "not deployed": Task Scheduler already points at this
file, so the next scheduled run (2026-09-16 03:15 Pacific, per the facts
above) will use this version automatically. Once the lead is ready for a
controlled manual run (e.g. once Mosquitto/other prerequisites are
confirmed), the exact command is:

```
python scripts/daily-recovery.py
```

Expect `overall: "success"` in both `status.json` and `latest.json` with all
eight stages `ok` if everything (including cleanup) succeeds; a `"partial"`
`status.json`/`latest-influx.json`-only outcome naming the first failing
stage otherwise, with `latest.json` left at its previous value. No cleanup
candidates were deleted and no MQTT/broker state was touched by this task.
