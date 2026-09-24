# Ryzen log collector (Grafana Alloy v1.19.2)

Staged, unapplied collector for the household observability M3 pilot
(`grafana/pilot/CONTRACT.md`, `grafana/docs/household-observability/architecture-2026-09-16.md`
sections 3.2, 3.3, 3.5, 3.8, 7; Codex review C3 of 2026-09-16). Nothing here is live
until the attended steps below are run by David; every script has a non-elevated
`-Mode Preflight` that reports what it would do, and `pfirewall-acl.ps1` has a
non-elevated `-Mode Verify`. Evidence of the validation runs and the preflight outputs:
`grafana/docs/household-observability/evidence/m3/log-collectors-2026-09-16.md` and
`.../evidence/m3/collector-integration-2026-09-17.md`.

| File | What it is |
| --- | --- |
| `config.alloy` | The collector configuration. Sources: `pfirewall.log` (`source=winfw`; the `.old` target is commented out, recovery-only), Security / LSM / RCM / RdpCoreTS / Firewall-policy / System-104 channels (`winsec`, `winlsm`, `winrcm`, `winrdpcore`, `winfwpolicy`, `winsys`), router syslog on `192.168.1.100:1514/udp` (`owrt-fw`, `dropbear`), the gateway container log (`gateway`), Alloy's own warnings (`alloy`). No journald source (that is the Pi/Threadripper pipeline). Pushes to `https://192.168.1.100:3443/loki/api/v1/push` as `alloy-ryzen` with the gateway CA. Labels are exactly `host, source, action, direction, proto, class`; everything else is structured metadata; Windows messages and EventData XML never leave the host (the stored line is rebuilt from extracted fields). |
| `install-alloy.ps1` | `-Mode Preflight|Apply|Rollback|UpdateConfig`, `-RuntimeAccount VirtualAccount|LocalSystem` (default `VirtualAccount`). **UpdateConfig** (elevated): validate this directory's `config.alloy` with the installed binary, back up the installed copy under `backups\`, copy, re-grant the service SID read, `POST /-/reload` (no service restart, no `collector-restart` mark; restores the previous config if the reload is refused). Installs the service, config at `C:\ProgramData\GrafanaLabs\Alloy\config.alloy`, secrets under `...\secrets`, starts and checks `/-/ready`. `VirtualAccount` = `NT SERVICE\Alloy` + Event Log Readers + read ACLs (the approved least-privilege path). `LocalSystem` = the conditional fallback: it refuses without `-Evidence <post-rotation Verify transcript>` and locks binaries, config, data and secrets to SYSTEM + Administrators (no user write). |
| `pfirewall-acl.ps1` | `-Mode Preflight|Verify|Apply|Rollback`. Apply: read grant on `%SystemRoot%\System32\LogFiles\Firewall\` and both log files for `NT SERVICE\Alloy` and `NT SERVICE\telegraf` (by service SID), `icacls /save` first. **Verify (read-only, any user):** current DACL of the directory and both files, whether the two service SIDs (and SYSTEM) hold read, the file creation/rotation times, and whether Alloy's `winfw` positions file (`data\loki.source.file.winfw\positions.yml`) advanced since the last rotation. |
| `audit-settings.ps1` | Decision D5: `auditpol` Logon S/F, Logoff S, Other Logon/Logoff Events S/F, Account Lockout S/F; Security log 128 MB; LSM/RCM/RdpCoreTS 16 MB; firewall log cap 32767 KB on the three profiles; `auditpol /backup` and recorded sizes first. |

The inbound firewall rules (TCP 3443 from the collectors, UDP 1514 from the router) are
a Networking-owner item: `grafana/pilot/host/ryzen/log-gateway-firewall.ps1` (proposal).

## Attended commands (administrator PowerShell, in this order)

```powershell
cd C:\Users\david\Repos\iot-backend\host\alloy
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-alloy.ps1 -Mode Preflight     # any user
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-alloy.ps1 -Mode Apply         # elevated (VirtualAccount)
powershell -NoProfile -ExecutionPolicy Bypass -File .\pfirewall-acl.ps1 -Mode Apply         # elevated, AFTER install-telegraf.ps1 (icacls maps a service SID only once the service exists; re-run after the second install)
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-alloy.ps1 -Mode UpdateConfig  # elevated, after a config.alloy change
powershell -NoProfile -ExecutionPolicy Bypass -File .\audit-settings.ps1 -Mode Apply        # elevated
# ... wait for one pfirewall.log rotation (about 4.5 h at 8 MB, about 18 h at 32 MB), then:
powershell -NoProfile -ExecutionPolicy Bypass -File .\pfirewall-acl.ps1 -Mode Verify        # any user, read-only; keep the output
```

Preconditions for Apply: the gateway bootstrap has produced `ca.crt` and
`alloy-ryzen.password` in `C:\Users\david\.grafana-recovery-keys\household-gateway\`
(the scripts only test existence, never print them); the log gateway is up so
`grafana\pilot\logs\gateway\` exists (otherwise re-run the `icacls` grant printed by
Apply once it does); the firewall rules are in place before expecting router or
Pi/Threadripper traffic.

| Script | Expected effect | Rollback |
| --- | --- | --- |
| `install-alloy.ps1 -Mode Apply` (default `-RuntimeAccount VirtualAccount`) | Downloads `alloy-installer-windows-amd64.exe` (sha256 `72b19a3f...` from the v1.19.2 `SHA256SUMS`), silent install with `/CONFIG=`, service `Alloy` running as `NT SERVICE\Alloy`, member of Event Log Readers, `/-/ready` reports ready; transcript and backups under `C:\ProgramData\GrafanaLabs\Alloy\backups\`. | `-Mode Rollback`: stops the service, runs `uninstall.exe /S`, removes the group membership; keeps `data\` (positions, bookmarks), `secrets\`, `config.alloy`, `backups\`. |
| `install-alloy.ps1 -Mode Apply -RuntimeAccount LocalSystem -Evidence <path>` | **Only after** `pfirewall-acl.ps1 -Mode Verify`, run after a real rotation that followed `pfirewall-acl.ps1 -Mode Apply`, shows the Alloy SID without read on the new `pfirewall.log` and the `winfw` positions not advancing; and only after `install-alloy.ps1 -Mode Rollback` of the VirtualAccount install (Apply refuses an existing service; Rollback keeps `data\` positions and `secrets\`, so the re-install starts shipping as soon as it is up). Same install, but the service keeps the installer's LocalSystem identity (no `sc.exe config`, no Event Log Readers), `C:\ProgramData\GrafanaLabs\Alloy` (config, data, secrets, backups) is reset to SYSTEM + Administrators full control only (subtree inherits; `NT SERVICE\telegraf` read on `data\` re-granted when that service exists), the binaries under `C:\Program Files\GrafanaLabs\Alloy` keep the Program Files default (SYSTEM/Administrators/TrustedInstaller full, Users read/execute, **no user write**) and Apply refuses if that directory or the ProgramData tree carries a non-admin write ACE; the evidence path + sha256 go into the transcript. No Network Configuration Operators membership, no WFP collection. After this Apply run `pfirewall-acl.ps1 -Mode Verify` **elevated** (a non-elevated run can no longer read `data\` or the Apply history and says so). | `-Mode Rollback -RuntimeAccount LocalSystem`: same as above; the SYSTEM/Administrators-only ACL on the ProgramData tree stays (data, secrets, backups kept). |
| `pfirewall-acl.ps1 -Mode Apply` | `icacls /save` of the Firewall log directory, then read ACEs for both service SIDs on the directory (inheritable) and on both files. Add-only. | `-Mode Rollback`: `icacls /restore` from the latest saved ACL file (or removes the two SIDs). |
| `pfirewall-acl.ps1 -Mode Verify` | Read-only report (DACLs, per-SID read, rotation marker = `pfirewall.log.old` LastWriteTimeUtc, positions verdict). Distinguishes the pre-Apply baseline (no Apply recorded) from a grant that survived and from a grant lost at a rotation that followed Apply. | none (no change) |
| `audit-settings.ps1 -Mode Apply` | Audit subcategories and channel sizes per D5; firewall log cap 32767 KB (cmdlet maximum, D5c "32 MB"). `LogAllowed` untouched (D5b). | `-Mode Rollback`: `auditpol /restore` + sizes restored from the recorded JSON. |

## Runtime identity: what is observed, what is predicted (Codex C3)

- **Observed (2026-09-16, non-elevated `Get-Acl`):** `pfirewall.log` and `pfirewall.log.old`
  carry a **protected DACL written by `mpssvc`** (SYSTEM, Administrators, Network
  Configuration Operators, `NT SERVICE\mpssvc`; no inherited ACEs, on both the current file
  and the one created by the 15:18 PDT rotation). The directory's inheritable ACE therefore
  does not reach the files.
- **Predicted, not yet observed:** the explicit file grant that `pfirewall-acl.ps1 -Mode
  Apply` adds is *expected* to be dropped when `mpssvc` creates the next `pfirewall.log`
  at rotation. Nothing has been applied, so no grant has been lost; there is no executed
  finding. `-Mode Verify` after the first post-Apply rotation settles it either way (the
  `.log` tailer may also keep reading through its already-open handle until Alloy restarts,
  which Verify calls out).
- **If the loss is observed:** the documented fallback is `install-alloy.ps1 -Mode Rollback`
  (VirtualAccount) followed by `install-alloy.ps1 -Mode Apply -RuntimeAccount LocalSystem`
  with the Verify transcript as `-Evidence`, protected binaries/config/secrets, and
  consistent Preflight/Rollback (above); from then on Verify runs elevated. Network
  Configuration Operators membership for the virtual accounts and any WFP collection are out
  of scope (C3).
- **Telegraf visibility is separate:** a LocalSystem Alloy does not give `NT SERVICE\telegraf`
  read on the log. `iot-backend/host/telegraf/exec/source-progress.ps1` reports
  `source_progress,source=winfw state="unknown" reason="log-unreadable (NT SERVICE\telegraf
  lacks read; pfirewall-acl.ps1 or the protected DACL)"` until the telegraf grant is in effect,
  and `source=winsec` its own `channel-unreadable (... not in Event Log Readers ...)` row; both
  rows are always emitted.

## Known limits (verified 2026-09-16, details in the evidence files)

- `.old` tailing is commented out (recovery-only): with Loki's staged `max_chunk_age: 2h`
  most re-read `.old` lines are older than the 1 h out-of-order window and are answered
  with `400 entry too far behind` while Alloy counts the whole batch in
  `loki_write_dropped_entries_total`; the `.log` tailer survives rotation on its own
  (`FILE_SHARE_DELETE`, drain, reopen). Lines that reappear in `.old` hash to the same
  `event_id` as their `.log` originals.
- Windows `event_id` is `ryzen:<channel>:<record_id>` without the generation counter;
  the aggregator derives the generation from Security 1102 / System 104 rows (or marks the
  identity uncertain, per Codex C2).
- Router entries use the receive time (`inferred=ts`); the fw4 `log prefix` format
  decides `action`/`zone`/`rule_name` and is confirmed by the Networking owner under D4.
- The syslog listener binds `192.168.1.100:1514`; if the Wi-Fi address is not up when
  the service starts, that component stays unhealthy until Alloy is restarted.
- `pfirewall.log`'s NTFS CreationTime is not a rotation marker: the file created by the
  rotation inherits the renamed file's creation time (name tunneling; both files showed
  `2026-09-16T17:40:34Z` while `.old` was last written at `22:18:31Z`). Verify uses
  `pfirewall.log.old` LastWriteTimeUtc.
