# Native Telegraf on the Ryzen (household observability M3, staged 2026-09-16)

Telegraf 1.40.0 (Windows amd64 zip, SHA256 pinned in `install-telegraf.ps1`) as the
Windows service `telegraf` running as the virtual account `NT SERVICE\telegraf`
(architecture §3.7/§7, D11: **no `docker-users`**, the Docker container input is
omitted), writing bucket `infra` on `http://localhost:8086` with the write-only token
`telegraf-ryzen`. Every row carries `host=ryzen observer=ryzen`. This is separate from
the container collector `iot-backend/telegraf/telegraf.conf`, which is untouched.
**Staged and unapplied**; `install-telegraf.ps1 -Mode Preflight` was run non-elevated on
2026-09-16 (see `grafana/docs/household-observability/evidence/m3/host-telemetry-2026-09-16.md`).

## Files → deployed paths

| File | Deployed as | Notes |
| --- | --- | --- |
| `telegraf.conf` | `C:\ProgramData\telegraf\telegraf.conf` | no outputs, no secrets; `logtarget=file` |
| `telegraf.d\influxdb-output.conf.example` | `C:\ProgramData\telegraf\telegraf.d\influxdb-output.conf` | the **only** file with the token; ACL SYSTEM/Administrators F, `NT SERVICE\telegraf` R, inheritance off, set before the content is written |
| `exec\lp.ps1` + 5 scripts | `C:\ProgramData\telegraf\exec\` | run by `inputs.exec` as the service account |
| `..\monitoring\service_health.ps1` | `C:\ProgramData\telegraf\monitoring\service_health.ps1` | evaluator; manifest stays in the repo |
| `install-telegraf.ps1` | run from the repo | `-Mode Preflight` (non-elevated) / `Apply` / `Rollback` (elevated) |

Directories: `state\` (source-progress memory, service-health snapshot; account has
Modify), `logs\` (Telegraf log; Modify).

## What is collected (interval 60 s)

| Input | Measurements | Notes |
| --- | --- | --- |
| `win_perf_counters` | `win_cpu win_mem win_disk win_net win_system` | Processor, Memory, LogicalDisk, Network Interface, System |
| `mem disk system internal` | standard | |
| `win_services` | `win_services` for `com.docker.service Alloy telegraf W32Time` | `com.docker.service` is Stopped/Manual on this host while the Engine runs (Docker Desktop backend runs in the user session): Stopped ≠ Docker down |
| `exec\service-health.ps1` | `service_health service_check service_dependency` | manifest `C:\Users\david\Repos\iot-backend\config\monitoring\dependencies.json`; timeout 50 s > budget 20 s |
| `exec\logging-state.ps1` | `logging_state,fw=winfw,profile=<domain|private|public>` | `enabled log_blocked log_allowed log_path cap_kb` + `log_readable audit_error` (additive); `audit_logon/audit_logoff` = `unknown (needs elevation)` |
| `exec\source-progress.ps1` | `source_progress,source=<winfw|winsec|winsys|winlsm|winrcm|winrdpcore|winfwpolicy>` + `reason` | positions.yml / bookmark.xml under `C:\ProgramData\GrafanaLabs\Alloy\data` vs `pfirewall.log` size / newest RecordId; state in `state\source-progress.json`. One row per source on every run, whatever fails (Codex C3): `winfw` is `unknown` with `reason="log-unreadable (<identity> lacks read; pfirewall-acl.ps1 or the protected DACL)"` until the service account can open the log for read (a directory-entry `Length` is not evidence); `winsec` is `unknown` with `reason="channel-unreadable (<identity> not in Event Log Readers; install-telegraf.ps1 -GrantEventLogReaders)"` without the group; an unexpected error yields `reason="exception:<type>"` |
| `exec\host-session.ps1` | `host_session,session_id=` `user type state since remote` | from `quser`; `remote="-"` (client address comes from Loki winrcm/winlsm) |
| `exec\clock-offset.ps1` | `clock_offset` `offset_s source synced` + `last_sync_age_s last_sync_error` (additive) | `w32tm /query /status /verbose` "Phase Offset" |
| every exec script | `exec_run,script=` `ok rows error` | additive; distinguishes "no rows" from "failed" |
| `inputs.prometheus` | Alloy `/metrics`, `metric_version = 1`, `collector=alloy` | connection errors until Alloy is installed |

## Token delivery: config fragment, not an environment variable

Chosen: `telegraf.d\influxdb-output.conf` holding the **whole** `[[outputs.influxdb_v2]]`
stanza (urls, org, bucket, token). Reasons: (1) a token-only fragment cannot work —
Telegraf treats every `[[outputs.influxdb_v2]]` table as its own plugin instance, so it
would add a url-less second output instead of merging (this is a deviation from the
task wording "a fragment holding only token"); (2) a service environment variable would
live in `HKLM\SYSTEM\CurrentControlSet\Services\telegraf\Environment`, which is readable
by local Users, while a file ACL can be limited to SYSTEM, Administrators and the
service identity; (3) `telegraf.conf` stays secret-free and byte-identical to git.
Apply creates the fragment empty, strips inheritance and grants first, then writes the
content, so the token is never world-readable through `C:\ProgramData`'s inherited
`Users:Read`.

## Permissions the collector identity gets at Apply

| Resource | Grant | Why |
| --- | --- | --- |
| `C:\ProgramData\telegraf` | RX; `state`, `logs`: Modify | config, snapshot/state, log file |
| `telegraf.d\influxdb-output.conf` | R (inheritance off) | token |
| `C:\Users\david\Repos\iot-backend\config\monitoring` | (OI)(CI)R | manifest by full path (Bypass Traverse Checking covers the parent dirs) |
| `C:\ProgramData\GrafanaLabs\Alloy\data` (if present) | (OI)(CI)R | positions.yml / bookmark.xml (log-collector territory, read only; re-run after Alloy is installed) |
| Event Log Readers | **not granted** unless `-GrantEventLogReaders` | Security newest RecordId for winsec progress |
| `docker-users` | never | D11 |
| firewall log directory | not granted here | the log-collector worker's `pfirewall-acl.ps1` grants `NT SERVICE\telegraf` read; `logging_state.log_readable` shows when it is in effect |

## Unknown by design until a grant or an install happens

| Series | Value now | Becomes real when |
| --- | --- | --- |
| `logging_state.audit_logon/audit_logoff` | `unknown (needs elevation)` — `auditpol` needs SeSecurityPrivilege (`Error 0x00000522`); permanent for this identity | never for this collector; read once at an attended elevated step (log-collector's `audit-settings.ps1`) |
| `source_progress,source=winsec` | `unknown`, `channel-unreadable (NT SERVICE\telegraf not in Event Log Readers; install-telegraf.ps1 -GrantEventLogReaders);bookmark_absent` | `-GrantEventLogReaders` (and Alloy's bookmark) |
| `source_progress,source=win*` (others) | `unknown`, `bookmark_absent` | Alloy installed (bookmark.xml exists) + Alloy data read grant |
| `source_progress,source=winfw` | `unknown`, `log-unreadable (NT SERVICE\telegraf lacks read; pfirewall-acl.ps1 or the protected DACL);alloy_positions_absent` | a read grant that survives rotation (`pfirewall-acl.ps1`, verified with `-Mode Verify`) + Alloy's positions.yml; elevating Alloy alone does not clear it (Codex C3) |
| `logging_state.log_readable` | `false` | `pfirewall-acl.ps1` (log-collector worker) |
| `win_services` rows for `Alloy`, `telegraf` | none (missing service logs an error) | the two installs |
| Alloy self-metrics | none | Alloy installed |

## Attended apply (David, elevated PowerShell)

```powershell
cd C:\Users\david\Repos\iot-backend\host\telegraf
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-telegraf.ps1 -Mode Preflight          # non-elevated is fine
# prerequisite: iot-backend\tools\provision_household.py --apply created secrets\household-telegraf-ryzen-token.json
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-telegraf.ps1 -Mode Apply              # elevated; add -GrantEventLogReaders to enable winsec progress
Get-Service telegraf; Get-Content C:\ProgramData\telegraf\logs\telegraf.log -Tail 20
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-telegraf.ps1 -Mode Rollback           # elevated
```

Apply order matters: service install → `sc.exe sidtype ... unrestricted` →
`sc.exe config ... obj= "NT SERVICE\telegraf"` → ACLs (the SID resolves only after the
service exists) → fragment ACL → fragment content → `--test` → start. Verify in Influx:
`from(bucket:"infra") |> range(start:-10m) |> filter(fn:(r)=> r.host=="ryzen")`.

## Deviations from the task/CONTRACT wording (reported in the return note)

1. PowerShell 5.1 port instead of `service_health.py` (per-user Python).
2. `logging_state` gains tag `profile` (one row per firewall profile would otherwise
   collapse into one series) and fields `log_readable`, `audit_error`.
3. `source_progress` gains field `reason`; `clock_offset` gains `last_sync_age_s`,
   `last_sync_error`; new measurement `exec_run`.
4. The token fragment carries the whole output stanza (see above).
5. `docker_container`, `derived` and delegated checks are "unprobed" outcomes that do
   not poison a service's combined state (agreed with the coordinator on 2026-09-16).
