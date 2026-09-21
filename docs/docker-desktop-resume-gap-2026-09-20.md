# Docker Desktop resume gap: iot-mosquitto after reboots

Recorded 2026-09-20 (Claude Opus 5, task `claude-opus5-ha-health-fix-20260920`).
Follow-up to `docs/mqtt-outage-2026-09-16.md`, which diagnosed the first
occurrence and recommended `docker start iot-mosquitto` as the recovery.

## Pattern (three occurrences in six days)

| Ryzen boot (PDT) | `iot-mosquitto` | `iot-influxdb` | `iot-telegraf` |
|---|---|---|---|
| 2026-09-14 22:05 | Exited (255) at 22:07, never resumed | resumed at 22:18 login | restart-looping on `lookup mosquitto: no such host` |
| 2026-09-18 09:39 | Exited (255) at 09:39, never resumed | resumed | restart-looping |
| 2026-09-19 23:04 | still Exited from 09-18 | resumed | restart-looping |

All three services carry `restart: unless-stopped`. Docker Desktop on this PC is
a user-session application, so nothing resumes until sign-in, and at sign-in
its restart-policy handling brings back `iot-influxdb` and `iot-telegraf` but
not `iot-mosquitto` (`RestartCount` stays 0: never attempted, not crash-looping).
Telegraf's loop is a symptom: Docker's embedded DNS only resolves a running
service. Home Assistant is not an MQTT client of this broker (its link to the
stack is the `influxdb:` history writer), so HA entities are not affected; the
MQTT -> Telegraf -> InfluxDB path is.

## Fix

- Immediate (each occurrence): `docker start iot-mosquitto`, then confirm
  `iot-telegraf` settles to `Up` within ~2 minutes (verification steps in
  `docs/mqtt-outage-2026-09-16.md`).
- Durable: `scripts/ensure-iot-containers.ps1` starts any of
  `iot-mosquitto`, `iot-influxdb`, `iot-telegraf` (broker first) that is not
  running and has an `unless-stopped`/`always` policy, after waiting up to
  10 minutes for the engine. Dry run unless `-Apply`; logs one line per
  container to `%LOCALAPPDATA%\iot-backend\ensure-iot-containers.log`
  (no secrets: names and states only).
  `scripts/install-ensure-task.ps1` registers it as the scheduled task
  "IoT Backend Ensure Containers" at logon of the current user with a 2-minute
  delay, Limited run level, 15-minute execution limit, same pattern as
  `install-recovery-task.ps1`. Registration is a standing change to this PC
  and was **not** performed by the recording session.

```powershell
# from C:\Users\david\Repos\iot-backend
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ensure-iot-containers.ps1          # dry run
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ensure-iot-containers.ps1 -Apply   # start now
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-ensure-task.ps1            # register logon task
```

Dry run on 2026-09-20 09:07 PDT: `iot-mosquitto: exited; would start`,
`iot-influxdb: running`, `iot-telegraf: restarting; would start`.

## Lifecycle

- Owner: iot-backend. Dependencies: Docker Desktop signed-in session.
- Health: the household service-health evaluator on this PC
  (`host/monitoring/service_health.ps1`) already reports the containers'
  states to Grafana; a broker that stays down is visible there. The task's log
  file is the audit trail for what the task did.
- Rollback: `Unregister-ScheduledTask -TaskName 'IoT Backend Ensure Containers'`.
  The script never stops, recreates or reconfigures containers.
- Open: why Docker Desktop skips this one container is not established; if it
  recurs with the task in place, capture `docker events` right after login.
