# MQTT outage — read-only investigation, 2026-09-16

Worker: read-only MQTT-outage investigator, reporting to lead
`claude-fable-monitor-closeout-20260916` (holds claims; `coordinate.py` not used
by this worker). Scope: sanitized diagnosis only. No container start/stop/restart,
no state-changing `docker compose`, no git changes; no environment values,
passwords or tokens were printed (`docker inspect` used only with explicit
`--format` fields, never full/`Env` output).

## Timeline (UTC, sanitized evidence)

| Time | Event | Evidence |
|---|---|---|
| ~2026-09-14 21:52 – 2026-09-15 04:53 | Mosquitto healthy, routine 30-min persistence saves | `docker logs -t iot-mosquitto`: regular `Saving in-memory database…` lines every ~30 min through `2026-09-15T04:53:03Z`, then nothing |
| 2026-09-15 05:05:49 | **Windows host boot time** | PowerShell `Get-CimInstance Win32_OperatingSystem \| Select LastBootUpTime` → `9/14/2026 10:05:49 PM` local (Pacific, UTC-7) = `2026-09-15T05:05:49Z` |
| 2026-09-15 05:07:26 | **`iot-mosquitto` recorded exited**, code 255, no clean-shutdown log line | `docker inspect iot-mosquitto --format '{{.State.Status}} {{.State.ExitCode}} {{.State.Error}} {{.State.FinishedAt}} {{.RestartCount}} {{.HostConfig.RestartPolicy.Name}}'` → `exited 255  2026-09-15T05:07:26.28Z 0 unless-stopped`. Log tail ends mid-cycle at 04:53; mosquitto's normal SIGTERM "…terminating" line never appears. |
| 2026-09-15 05:18:19 (local proc start, ≈05:18 UTC) | Docker Desktop process (re)started | PowerShell `(Get-Process 'Docker Desktop').StartTime` → `9/14/2026 10:18:19 PM` local (five processes, same second) |
| 2026-09-15 05:18:32 | **`iot-influxdb` fresh start**, `RestartCount 0` | `docker inspect iot-influxdb --format '{{.State.Status}} {{.State.StartedAt}} ...'` → `running 2026-09-15T05:18:32.95Z ... RestartCount=0` — essentially the same second as Docker Desktop's own relaunch |
| 2026-09-15 10:15:01 | Scheduled recovery job runs, MQTT stage fails | `schtasks /query /tn "IoT Backend Verified Encrypted Recovery" /fo LIST /v` → `Last Run Time: 9/15/2026 3:15:01 AM` (Pacific) = 10:15 UTC, `Last Result: 1`. `D:\Backups\iot-backend\mqtt-20260915T101546Z\` exists but is **empty (0 files)** — `docker kill --signal SIGUSR1 iot-mosquitto` failed immediately against an already-stopped container, before it could write anything |
| 2026-09-15 23:41–23:43 | Two manual recovery runs, same MQTT-stage failure | `mqtt-20260915T234207Z/` and `mqtt-20260915T234322Z/` also empty (0 files) |
| now (2026-09-16) | `iot-telegraf` still restart-looping | `docker inspect iot-telegraf` RestartCount climbing (1299 at last check); `docker logs --tail 5 iot-telegraf` ends `dial tcp: lookup mosquitto on 127.0.0.11:53: no such host` — Docker's embedded DNS only resolves a *running* service, so this is a symptom, not an independent fault |

`docker events` for both `iot-mosquitto` and `iot-influxdb` over `2026-09-15T00:00Z`–`12:00Z`, and system-wide `04:50–05:15Z`, returned **no records** — the event ring buffer does not survive a Docker Desktop/engine restart, so the actual stop/die/kill signal itself is not directly observable; the conclusion below rests on timing correlation, not a captured event.

## Most likely cause (medium-high confidence)

**An unplanned Ryzen host restart around 2026-09-15 05:05–05:07 UTC**, not the
recovery job. Three independent, correlated timestamps: the OS boot time
(05:05:49), Docker Desktop's own process relaunch (~05:18:19), and
`iot-influxdb`'s fresh `StartedAt` (05:18:32, `RestartCount 0`, i.e. a new start
adopted at daemon startup, not a policy-triggered restart) — all cluster tightly
around the same event. `iot-mosquitto`'s exit (05:07:26, code 255, no graceful
shutdown log, `RestartCount 0`) falls inside that same window. Exit code 255
with no "terminating" line is consistent with the container being killed
abruptly as the Desktop/WSL2 VM went down for the reboot, not a normal
`docker stop`/SIGTERM.

The gap needing more confidence: **why `iot-influxdb` (and, per its active
restart-loop, `iot-telegraf`) resumed automatically while `iot-mosquitto` did
not**, despite identical `restart: unless-stopped` policy. `RestartCount 0` on
mosquitto means Docker's restart-policy engine never even attempted to bring it
back — it isn't crash-looping, it's simply not being retried. This matches a
known Docker Desktop/Windows behavior gap (not every previously-running
container is reliably resumed after a Desktop/WSL restart) rather than any
mosquitto-specific config defect; `mosquitto.conf`'s `persistence true` /
`persistence_location /mosquitto/data/` / `log_dest file ... + stdout` settings
are unremarkable, and the same named volumes (`mosquitto_data`, `mosquitto_log`)
were mounted read-write with no evidence of a permissions problem.

**The recovery job's `SIGUSR1` is ruled out as the original cause**, not just
deprioritized:
- No `mqtt-recovery.py` output directory exists anywhere near 05:0x UTC on
  2026-09-15 — the nearest runs are 10:15 UTC (3+ hours later) and 23:4x UTC,
  both **after** the broker was already down, and both produced only empty
  output directories because `docker kill` failed instantly on a stopped
  container (matches the diagnosis already on record in
  `docs/recovery-job-2026-09-15.md` and `docs/infra-monitoring-2026-09-15.md`).
- The identical `docker kill --signal SIGUSR1 iot-mosquitto` call ran
  successfully against the live production broker on four consecutive prior
  days (`mqtt-20260911T073853Z` through `mqtt-20260914T101549Z`, each a
  complete non-empty `encrypted.tar` + `verification.json`) with no crash, so
  SIGUSR1 itself is not broker-fatal in this deployment.

No other repo (trmnl, threadripper, homeassistant) documents an intent to stop
Mosquitto around 2026-09-15; `threadripper/docs/monitoring-reliability-2026-09-15.md`
independently lists "Restart Mosquitto on Ryzen" as a pending user-gated
decision, consistent with this finding rather than contradicting it.

## Is restarting safe?

Yes, restarting the existing container is safe and does not touch config or
data: no evidence of corruption (persistence file save cycles were clean and
regular right up to 04:53; the container was killed, not the data). No
production client action or endpoint change is implied.

**Recommended command:** `docker start iot-mosquitto`
(not `docker compose up -d --no-deps mosquitto`, and not a full
`docker compose up -d`.) `docker start` resumes the *existing* stopped
container exactly as it was (same image, mounts, config) with zero recreation
risk. `docker compose up -d --no-deps mosquitto` would recreate the container
from the current `docker-compose.yml`/`.env` if Compose thinks anything
differs — safe here since nothing changed, but it also re-resolves the image
tag and re-attaches mounts, a needless extra step when the original container
is intact. A bare `docker compose up -d` (no `--no-deps`/service arg) should be
avoided for this fix: it would reconcile *all* services against current
Compose state, including `iot-telegraf` and `iot-influxdb`, which are
unrelated to this outage and could pick up unintended drift (e.g. any
uncommitted `.env`/compose edits) at the same time.

## Post-restart verification (for the lead to run)

1. `docker logs --tail 20 iot-mosquitto` — expect a normal startup line
   (listener bind on 1883/9001, no immediate error) with no repeated crash.
2. `docker ps` after waiting ~2 minutes — `iot-telegraf` should stop
   restart-looping and settle to `Up`.
3. `docker logs --tail 5 iot-telegraf` — should no longer show
   `lookup mosquitto ... no such host`.
4. `docker logs iot-mosquitto` (recent window) — expect connection lines for
   the two configured/expected clients: Telegraf (subscriber) and, per
   `README.md`, the Arduino Uno R4 WiFi publisher (`MQTT_USER`/`MQTT_PASSWORD`
   from `.env`) — note the Arduino has been silent since 2025-12-31 per prior
   history, so its absence here would not be a new problem. Home Assistant's
   integration to this stack is via the `influxdb:` block, not MQTT, so it is
   not an expected MQTT client.
5. Only then: the lead runs `python scripts/daily-recovery.py` once, as a
   controlled end-to-end check (per `docs/recovery-job-2026-09-15.md`'s fixed
   per-stage status handling), and confirms `overall: "success"` with all six
   stages `ok` in `status.json`/`latest.json`.

## Note on `mqtt-recovery.py`'s own robustness (proposal only, not this worker's path)

Independent of today's root cause, `mqtt-recovery.py` line 24
(`docker kill --signal SIGUSR1 iot-mosquitto`) has no guard for the broker
already being stopped, so any future outage will keep aborting the daily job
at this exact first line instead of failing informatively or skipping
cleanly. Minimal proposed fix (for the actual script owner to implement):
check `docker inspect iot-mosquitto --format '{{.State.Running}}'` before the
kill and raise a clear, distinct "broker not running" error (or a distinct
skip status) rather than letting the generic `RuntimeError` from `command()`
propagate. Test coverage for this would be a unit test in
`tests/test_daily_recovery.py`-style mocked `subprocess` fixture asserting
that a `Running=false` broker produces the new distinct status/exception
instead of the current generic failure, alongside the existing "kill succeeds"
happy path.
