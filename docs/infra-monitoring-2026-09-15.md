# Infra bucket and Threadripper monitoring credentials — 2026-09-15 UTC

Status: implementation complete for the consolidated-credential design
(coordinator-approved), tested with mocks and a real read-only dry run
against the live instance. **No `--apply` has been run in this task; no
bucket, token or credential file exists yet.** Coordinator: Codex, task
`threadripper-monitor-plan-20260915`. Worker:
`claude-sonnet-infra-provision-consolidated-20260915`. Scope per
[the monitoring plan](../../threadripper/docs/monitoring-plan-2026-09-15.md):
this repo owns InfluxDB lifecycle, bucket permissions and backup for the new
`infra` bucket. Threadripper's own collector config is a separate worker's task.
Grafana's `.env`/datasource provisioning is that repo's own workflow and is
explicitly out of scope here — see [Handoff](#handoff) below.

> **Update 2026-09-15, after 23:45 UTC (lead `claude-fable-monitor-lead-20260915`,
> recorded by a documentation worker):** the status above is superseded and kept
> for the record. `--apply` has run (bucket, both tokens and both credential
> files exist), Grafana activated the consolidated reader at 23:37:56 UTC, and
> the off-host credential export (D2) and the credential restore drill (D3) are
> now completed with evidence. See
> [Post-deploy evidence, 2026-09-15](#post-deploy-evidence-2026-09-15) and the
> annotation under [Off-host recoverability](#off-host-recoverability--corrected).
> Two caveats stand: the daily job still fails at the MQTT stage after the
> Influx part lands, and the Threadripper-held restic key is documented from
> 2026-09-11, not re-verified today. Both caveats are followed up in
> [Reliability pass, 2026-09-16](#reliability-pass-2026-09-16). *[Both caveats
> closed 2026-09-16; see [Closeout, 2026-09-16](#closeout-2026-09-16).]*

## Closeout, 2026-09-16

Recorded by a documentation worker for lead `claude-fable-monitor-closeout-20260916`
from the lead's observations; no secret, record file, `latest.json` or archive was
opened by the worker. Times are UTC on 2026-09-16.

1. **Mosquitto restored, 05:40:44.** Cause established: an unplanned Ryzen host
   restart at 05:05:49 UTC on 2026-09-15 after which Docker never retried the
   container (`docs/mqtt-outage-2026-09-16.md`). Restored with
   `docker start iot-mosquitto` (existing container, no recreation); `iot-telegraf`
   reconnected to `tcp://mosquitto:1883` at 05:41:44 and stayed up.
2. **Recovery job proven end to end, controlled run 05:43 to 05:45.**
   `python scripts/daily-recovery.py`: all 8 stages ok, `latest.json` overall
   success, `latest-influx.json` written, staging removed. Off-host copies verified
   on Threadripper: `20260916T054357Z.tar` (sha256
   `0c338244c4c6f8b750c3b5df13284672d6cf33e3d80520fbab62888d52356a77`) and
   `mqtt-20260916T054357Z.tar` (sha256
   `51a9e9d32d8ad7f90f057092bd40b2e5a12ed63b109375e8ec7e2dc337813df8`). The next
   scheduled run (10:15 UTC) has not yet been observed, so the unattended schedule
   is still unproven.
3. **Threadripper-held key drill completed, about 06:21.**
   `scripts/verify-threadripper-checkpoint.py` against the Threadripper copy of
   checkpoint `20260915T234120Z` (archive sha256
   `483a7a9813ff8c9c83c92ef7013c0c0f94015e2b35bf6a626008e9f869d1d8db`). The first
   resume proved `restic check` and `restore --verify` with the root-only
   `/etc/influxdb-standby/backup-password` and restored both credential files with
   matching auth ids (`1155d1b0f9d87000` writer, `1155d1b13d987000` reader), reader
   probe 200 and writer probe 204, but the script accepted only 400 for the writer
   and reported failure; the rule now accepts 204 (matching
   `tools/provision_infra.py`) and is pinned by a test (container: 110 tests). A
   second drill in a fresh temp dir `/home/david/iot-drill-Baduuryd` passed:
   `ok: true`, snapshot
   `0c28249411ce8818c699edf41c1c0013fe1abb66ff762c26783ea2eb5ae3df21`, token-free
   record `data/iot-drill-Baduuryd-record.json`; the temp dir was removed (ordinary
   `shred` and `rm`, not guaranteed SSD erasure). Under Git Bash run the script with
   `MSYS_NO_PATHCONV=1`, otherwise the Linux path is rewritten. This closes the
   "match is inferred, not observed" caveat in
   [Off-host recoverability](#off-host-recoverability--corrected). Still not
   proven: restore of the Influx data itself from the Threadripper copy (only the
   credential files were restored) and any restore into the production container.
4. **Continuity-monitor cutover live.** `secrets/continuity-monitor.json` `url` set
   to `http://10.77.77.1:8086` (only that key changed). Because Threadripper has no
   repository checkout, the deploy went through a curated release built by the new
   threadripper `scripts/prepare-continuity-release.py` (23 tests):
   `continuity-20260916T055935Z`, applied by the user at about 06:20. The unit now
   sets `IPAddressAllow=10.77.77.1 192.168.1.100`; the monitor's 06:20:31 run exited
   0, the first success since at least 2026-09-12, and the Threadripper health
   snapshot at 06:22 shows `continuity-monitor` state 0 with upstreams
   `influx-ryzen` and `os` (manifest `monitoring-20260916T054444Z`, 29 services,
   45 edges, applied at about 06:21).
5. **Unchanged and deferred:** old reader `114cb64756347000` still active; the
   cleanup candidates (empty `mqtt-20260915T*` directories, `data/daily-*` staging)
   still wait for the user's go; nothing committed or pushed.

## Reliability pass, 2026-09-16

Recorded by a documentation worker for lead
`claude-fable-monitor-reliability-20260915` from the lead's observations and from
[recovery-job-2026-09-15.md](recovery-job-2026-09-15.md), the recovery-code worker's
report, which holds the full diagnosis, the fix and the test list. No secret, `.env`,
`latest.json` or archive was opened by the worker. Times are UTC.

1. **Root cause of the MQTT-stage failures: the broker is not running.** The
   `iot-mosquitto` container has been `Exited (255)` since 2026-09-15 05:07:26
   (`StartedAt` 2026-09-09 16:18:55, `OOMKilled: false`; its log ends at 04:53
   mid-cycle with no clean-shutdown line). Its restart policy is `unless-stopped` and
   its state is `exited`, not `restarting`, which is what Docker records after an
   external stop rather than a crash loop. `scripts/mqtt-recovery.py`'s first live
   action is `docker kill --signal SIGUSR1 iot-mosquitto`, which fails on a stopped
   container, so all three runs (10:15, 23:41, 23:42) aborted at that stage after the
   Influx checkpoint had already landed off-host. The Ryzen `iot-telegraf` restart loop
   (1086 restarts, `lookup mosquitto ... no such host`; Docker's embedded DNS resolves
   only a running service) is a symptom of the same condition, not a second fault.
   **Restarting Mosquitto is a user decision; no agent has done it.** Until then the
   scheduled job cannot fully succeed. *[Restored 05:40:44 UTC with the user's
   approval; see Closeout, item 1.]*
2. **`scripts/daily-recovery.py` fixed and tested, not yet exercised live.** Per-stage
   status (`influx_backup`, `encrypt`, `tar`, `offhost_copy`, `mqtt_export`,
   `mqtt_copy`) is written to `D:/Backups/iot-backend/status.json` on every exit path;
   `latest.json` becomes `overall: "partial"` with `failing_stage` and the verified
   Influx fields when only the MQTT stages fail, and is left byte-for-byte untouched
   when an earlier stage fails; the decrypted staging directory is removed as soon as
   the off-host copy is verified (same containment guard, earlier in the pipeline);
   failure evidence is a redacted, 20-line stderr tail (`token`/`password`/
   `Authorization` values and 32-plus-character hex or base64 runs removed). Nine
   tests in `tests/test_daily_recovery.py` with `subprocess` fully mocked. **No real
   run of the fixed job has happened**; the lead runs `python scripts/daily-recovery.py`
   once Mosquitto is back, expecting `overall: "success"` and all six stages `ok`.
   *[Done 05:43 to 05:45 UTC: all 8 stages (the script grew a preflight and a
   cleanup stage) ok, `overall: "success"`; see Closeout, item 2.]*
3. **The validation container now runs every unit test.** `tests/validate.sh`
   discovers `test_*.py` (the `integration_*.py` and `*_drill.py` files stay out) and
   `tests/Dockerfile` copies `tools/`, so `test_provision_infra.py`,
   `test_encrypt_checkpoint.py`, `test_verify_credential_restore.py` and the new
   `test_daily_recovery.py` run in the disposable `--network none` container. Result:
   **80 tests, all passing** (9 daily recovery, 6 encrypt checkpoint, 2 monitor, 55
   provision infra, 8 credential restore) plus the `py_compile`, Ansible syntax and
   render checks; the worker ran it and the lead re-ran it independently. This closes
   the open item in [Post-deploy evidence](#post-deploy-evidence-2026-09-15), item 3.
4. **Threadripper-held key drill prepared, awaiting one sudo step.** New
   `scripts/verify-threadripper-checkpoint.py` (design C3 in
   [Threadripper's audit](../../threadripper/docs/monitoring-recovery-2026-09-15.md)).
   The prepare phase ran at about 01:40 for checkpoint `20260915T234120Z`: temp
   directory `/home/david/iot-drill-GQOs1Ay3` on Threadripper, archive SHA-256 verified
   equal on both hosts. It now waits for the user's single interactive `sudo` restic
   step on Threadripper (the root-only `/etc/influxdb-standby/backup-password`), then
   `--resume`. Until that completes, "the Threadripper copy of the key unlocks the
   2026-09-15 tar" remains inferred from the 2026-09-11 record, as stated above.
   *[Completed at about 06:21 UTC in a fresh temp dir `iot-drill-Baduuryd`; the
   `GQOs1Ay3` directory was consumed by the first resume; see Closeout, item 3.]*
5. **Grafana checkpoint `20260915T235714Z` confirmed on both hosts:** 11 dashboard
   UIDs including `home-threadripper`, `restored_dashboard_uids_match` and
   `encrypted_restore_identical` true, an independent Threadripper copy with matching
   SHA-256 and a per-checkpoint key on both hosts (detail in the Threadripper audit's
   "Current state, 2026-09-16" section).
6. **Cleanup candidates, nothing deleted.** The three `mqtt-20260915T*` directories
   under `D:\Backups\iot-backend` are empty (0 files), and the three
   `data/daily-20260915T*` staging directories remain; both wait for the user's go.

## Read-only discovery (live, 2026-09-15)

- `iot-influxdb` container: `influxdb:2` tag, actual image `InfluxDB v2.7.12`
  (git `ec9dcde5d6`), matching the pinned checkpoint in
  [recovery and continuity](recovery-and-continuity-2026-09-11.md).
- Org `home` = `714f34e4c62e3500`. Buckets: `iot` (`dc846c7b25ee1436`,
  infinite retention), `network` (`57497837fc976b6f`, 90 d), `voice_telemetry`
  (`bf46fdb9d8a893fd`, infinite), plus system `_monitoring`/`_tasks`. **No
  `infra` bucket exists yet.**
- `influx auth list --org home` (permissions only; no token values read or
  printed): one operator token; three write-only producer tokens (Telegraf,
  Home Assistant, two network pollers, router); two read-only consumer tokens
  (Threadripper continuity monitor: `iot`+`network`; a Networking report:
  `network` only); and **one shared `grafana read-only (iot, network,
  voice_telemetry)` token** (`114cb64756347000`) that Grafana's datasource
  currently uses for all three buckets. Re-verified live during this task:
  its permission set is exactly `read` on `iot`, `network` and
  `voice_telemetry` — no unexpected or extra scopes.
- Observed but out of scope: `iot-telegraf` was mid-restart during discovery.
  Not touched; flagging for whoever owns the Telegraf/MQTT pipeline if it
  persists, since it is unrelated to this bucket-provisioning task.

## Design

`tools/provision_infra.py` (dry-run by default, `--apply` required for any
write) will, reusing `scripts/influx-recovery.py`'s `live()`/`command()`/
`private_directory()` helpers rather than duplicating them:

1. Create bucket `infra` in org `home` with 30-day retention, idempotent by
   name (skip if already present; fail loudly if present with a different
   retention rather than silently changing it).
2. Create one write-only Threadripper token scoped only to
   `write:orgs/<home>/buckets/<infra>`, idempotent by description (same
   check-existing-by-description pattern as `scripts/provision-monitor-token.py`).

## Grafana read-access decision (approved, implemented, not yet applied)

The plan says to extend Grafana's read access while preserving its existing
datasource UID and Flux queries. InfluxDB 2 authorizations are immutable sets
of permissions — there is no API to add a bucket to the *existing* shared
Grafana token. Two options were drafted in an earlier revision of this doc:

- **A. Additive:** a second, `infra`-only token as a second datasource
  credential.
- **B. Consolidated:** one new token carrying the union of the existing
  scope plus `infra`, replacing the old token's *use* in Grafana's
  datasource while leaving the old token itself untouched.

**Coordinator has reviewed and approved option B** (consolidated), with one
change from the original draft: **the old token is never revoked by this
script, under any circumstances.** It stays active indefinitely so the
Grafana datasource swap can be rolled back by simply reverting its `.env`.
Revocation, if ever wanted, is a manual decision for a human working
directly with `influx auth`, outside this tool.

Implementation (`tools/provision_infra.py`):

- `find_source_grafana_auth` locates the existing token by its known
  description (`grafana read-only (iot, network, voice_telemetry)`) and
  validates, **before any other planning**, that it is active and has
  *exactly* `read` on `iot`, `network` and `voice_telemetry` — no more, no
  less. An unexpected scope or an ambiguous/missing source token fails the
  whole run immediately.
- The new consolidated token's description is
  `grafana read-only (iot, network, voice_telemetry, infra)`; it is created
  with `read` on all four buckets.
- Handing the new token to Grafana's own provisioning (`.env` write,
  preserving the existing datasource UID) is that repo's workflow, not this
  script's. This script only produces the protected local credential file;
  see [Handoff](#handoff).

## Idempotence and credential-safety hardening

An earlier revision only checked description + active status before
treating a token as "already provisioned." That was insufficient: an
existing live token proves nothing about whether *this host* still holds a
usable copy of its secret, since InfluxDB never allows a token value to be
re-read after creation. `tools/provision_infra.py` now requires, before
treating any existing token as provisioned (and thus before deciding to
skip):

1. **Exact scope match.** The existing token's `permissions` must equal the
   intended set precisely — not a superset or subset — or the run fails
   loudly rather than silently accepting a drifted token.
2. **A matching local credential file**, keyed by `auth_id`, so a stale file
   left over from a deleted/recreated token is never mistaken for the right
   one.
3. **A harmless authenticated probe** of the saved token value — a
   zero-byte write for write-only tokens (a valid token gets HTTP 400 "bad
   request body", not 401/403, so nothing is actually written) or a `limit=1`
   bucket-list read for read-only tokens — confirming the saved secret still
   actually works, without ever writing data, logging the token, or
   returning its value to this script's caller.

If any of these fail — missing/corrupt/mismatched local file, or a probe
that comes back unauthorized — provisioning **fails clearly, before any
mutation**, rather than silently skipping or (worse) silently rotating the
token. This applies equally in dry-run and `--apply` mode, since the check
runs during planning: a dry run now distinguishes "nothing to do" from
"this token exists live but this host cannot prove it can use it."

Other hardening in the same pass:

- **Preflight before every token creation:** refuse to create a token if its
  target secret path (or the atomic-write `.tmp` path) already has an
  unexpected file sitting there, rather than silently overwriting it.
- **Atomic, exclusive-create writes at mode 0600** (`os.O_EXCL`, then
  `os.replace`). On Windows there is no per-file `icacls` call; the ACL
  comes from `secrets/`'s own inherited permissions, set once by
  `recovery.private_directory()` with `(OI)(CI)` inheritance flags, so any
  new file created inside inherits the same restricted ACL automatically.
- **Persist-before-validate:** a newly created token's secret is written to
  disk *immediately* after creation, before its status/permissions are
  checked. If a live-created token then turns out inactive or wrongly
  scoped, the run still fails (for manual review), but the only copy of its
  secret is not lost in the process. A failure to *write* that copy (e.g.
  disk full) is itself reported clearly, without ever including the token
  value, and explicitly notes the token is not recoverable from this script
  and was never revoked.
- **Shell-interpolation validation:** `org_id` and every `bucket_id` are
  validated against a 16-character-hex pattern before being spliced into any
  `docker exec ... sh -c` command string, independent of the existing
  `--org`/`--bucket` name validation.
- Fixtures in `tests/test_provision_infra.py` reuse the real, sanitized org
  and bucket IDs recorded above (rather than placeholder strings like
  `org1`) so test coverage reflects the actual shape of live
  `influx ... --json` output, including that `permissions` is a flat list of
  `"read:orgs/<id>/buckets/<id>"`-style strings.

## Tests and verification

`python -m unittest tests.test_provision_infra` — 53 tests, all passing.
*(2026-09-15 update: 55 after the test-isolation fix noted in
[Post-deploy evidence](#post-deploy-evidence-2026-09-15), item 3.)*
Mocks `recovery.live`/`recovery.command`/`recovery.private_directory`; token
writes exercise the real filesystem inside per-test temp directories, not
the real `secrets/`. Covers (in addition to the original bucket/token
planning and CLI-validation cases): rejection of a source Grafana token with
an unexpected or ambiguous scope; rejection of an existing token whose scope
has drifted from what's intended; a missing/corrupt/mismatched local
credential file failing clearly instead of silently skipping; a harmless
probe failure being treated the same way; a persistence failure after live
token creation being reported without the token value; a partial rerun
(bucket already created, one token already valid, the other still pending);
that the original shared Grafana token is never mutated and that no
`delete`/`revoke` command is ever issued; that no `main()` output (dry-run
or apply) ever contains a token value; and a fully-provisioned no-op dry run
that still performs (and passes) the local-credential probe rather than
trusting descriptions alone.

Also ran `python tools/provision_infra.py` for real (no `--apply`) against
the live `iot-influxdb` container in this task: correctly read org `home`
(`714f34e4c62e3500`), found the real `iot`/`network`/`voice_telemetry`
bucket IDs, validated the live shared Grafana token's scope as expected
(passed), saw no existing `infra` bucket or matching new-token descriptions,
and printed a `create` plan for the bucket and both tokens. Verified
afterward that `influx bucket list` still shows only the five pre-existing
buckets and that `git status --short --ignored secrets/` shows no change —
the dry run performed no live mutation.

## Post-deploy evidence, 2026-09-15

Recorded for lead `claude-fable-monitor-lead-20260915` from the lead's
observations (all times UTC, 2026-09-15) and from the verification files named
below, which the recording worker read directly. No secret file, `.env`,
`latest.json` or checkpoint archive was opened by the worker; token values
appear nowhere. Items marked "lead's observation" were not re-run.

1. **Apply and Grafana activation.** `tools/provision_infra.py --apply` had
   already run before the lead's session: bucket `infra` `883c17ff19b886d4`
   (30 d), writer `1155d1b0f9d87000` (`threadripper infra write-only, infra
   bucket`) and consolidated reader `1155d1b13d987000` (`grafana read-only
   (iot, network, voice_telemetry, infra)`); the old reader `114cb64756347000`
   is retained and active. Grafana consumed the new reader at 23:37:56 via
   `grafana/tools/activate_infra_reader.py`, keeping a rollback copy of the
   previous `.env` under `C:\Users\david\.grafana-recovery-keys\env-rollback\`
   (PC only); the container was recreated at 23:38 and all dashboards passed
   their query checks (lead's observation).
2. **D1 — post-creation backup and isolated restore, 23:30.**
   `python scripts/influx-recovery.py --out data/monitoring-postdeploy-20260915`
   passed. `data/monitoring-postdeploy-20260915/verification.json`
   (`observed_at` 2026-09-15T23:30:32Z): backup 4.953 s, restore and query
   17.953 s, `metadata_match`, `restart_verified` and `isolated` all true; six
   buckets including `infra` with `everySeconds: 2592000`; ten authorizations
   including `1155d1b0f9d87000` (single `write:` scope on `883c17ff19b886d4`)
   and `1155d1b13d987000` (four `read:` scopes), both `active`;
   `aggregate_query_results.infra` count **51,657**. This is the first proof
   that rows exist in `infra` and that the new metadata survives a restore.
3. **P1 and P2 implemented (uncommitted).** `scripts/encrypt-checkpoint.py`
   now also copies `secrets/threadripper-infra-token.json` and
   `secrets/grafana-infra-token.json` (optional, each recorded) beside the
   three required credentials, and `encryption-verification.json` gains
   `credentials_included`/`credentials_skipped`; `secrets/influx-restic-password`
   is still never included (comment at line 16). New
   `scripts/verify-credential-restore.py --checkpoint <dir>` restores only the
   two `*-infra-token.json` files from the checkpoint's restic repository
   inside a `--network none` container, probes each through
   `provision_infra.probe_saved_token` (harmless: empty-body write expecting
   HTTP 400, `limit=1` bucket list for read), prints only label / `auth_id` /
   description / `probe_ok` through a guard that refuses any output containing
   a restored token, and removes the container and private temp directory in
   `finally`. Tests: `tests/test_encrypt_checkpoint.py` +
   `tests/test_verify_credential_restore.py` 14 pass; `tests/test_provision_infra.py`
   55 pass after a test-isolation fix (secret output paths now patched into
   temp dirs). **Open item, not fixed:** `tests/validate.sh` discovers only
   `test_monitor.py` and `tests/Dockerfile` does not copy `tools/`, so the
   container validation run executes none of these tests (both files read).
   *(Fixed 2026-09-16: see [Reliability pass](#reliability-pass-2026-09-16), item 3;
   the container now runs 80 tests.)*
4. **D2 — encrypted off-host checkpoint, 23:41.** `python scripts/daily-recovery.py`
   completed the InfluxDB backup and isolated restore (staging
   `data/daily-20260915T234120Z/verification.json`, `observed_at` 23:41:52Z:
   `metadata_match`/`restart_verified`/`isolated` true, `infra` 30 d, all ten
   authorization ids, `infra` count 73,564), the encryption
   (`D:\Backups\iot-backend\20260915T234120Z\encryption-verification.json`:
   snapshot `0c282494…3f21`, `all_data_checked: true`,
   `restored_files_identical: true`, `credentials_included` = `iot.env`,
   `mosquitto-password.txt`, `influx-operator-token`,
   `threadripper-infra-token.json`, `grafana-infra-token.json`;
   `credentials_skipped: []`), the tar, and the independent copy to
   Threadripper `/home/david/iot-checkpoints/20260915T234120Z.tar` with
   matching SHA-256 `483a7a98…d8db` — then **failed at the pre-existing MQTT
   stage** (`scripts/mqtt-recovery.py`, invoked at `daily-recovery.py` line
   53), the same stage that failed the scheduled 10:15 run. Consequences:
   `D:\Backups\iot-backend\latest.json` still points at 2026-09-14 (lead's
   observation) and staging `data/daily-20260915T234120Z/` was left in place.
   The lead accidentally started a second run at 23:42; it produced a
   redundant but valid checkpoint `20260915T234235Z` (local directory,
   staging `data/daily-20260915T234235Z/` whose verification shows `infra`
   count 75,529, and Threadripper copy `20260915T234235Z.tar`) before failing
   at the same stage. Nothing was deleted; the cleanup candidates are listed
   in [Threadripper's audit](../../threadripper/docs/monitoring-recovery-2026-09-15.md#cleanup-candidates-need-the-users-go-nothing-deleted).
   The MQTT failure is outside monitoring scope and needs its own
   investigation; until it is fixed the *scheduled* job does not complete and
   `latest.json` does not advance.
5. **D3 — credential restore-and-probe drill, 23:45.**
   `python scripts/verify-credential-restore.py --checkpoint D:\Backups\iot-backend\20260915T234120Z`
   returned `ok: true`, snapshot `0c282494…3f21`; both credentials were
   restored from the encrypted checkpoint and probed successfully:
   `1155d1b0f9d87000` (write-only) and `1155d1b13d987000` (read-only) both
   `probe_ok: true`. No container or temp directory was left behind (lead's
   observation). The drill used the PC copy of the repository and the PC key
   `secrets/influx-restic-password`; it did not exercise the Threadripper tar
   or the Threadripper-held key.

**Restic key custody, from the record rather than assumption.**
[Recovery and continuity](recovery-and-continuity-2026-09-11.md) records a
root-only server key `/etc/influxdb-standby/backup-password` on Threadripper
beside the PC key `secrets/influx-restic-password` (2026-09-11 drill), and
`encrypt-checkpoint.py` lines 33–34 create the PC key only if it is missing,
so one key has encrypted every checkpoint since. That the Threadripper copy
equals the current PC key is therefore inferred from code and the 2026-09-11
record, not observed today; no `restic check` has been run on the server
against a 2026-09-15 tar. "Credentials recoverable off-host" currently rests
on that record, and a user-run server-side `restic check` would settle it.

## Off-host recoverability — corrected

An earlier revision of this doc claimed new authorizations were adequately
covered by "the next `influx backup`." **That overstated recoverability and
is corrected here:** an InfluxDB backup captures the KV metadata needed to
restore the *server's* view of an authorization, but the plaintext token
*value* is only ever returned once, at creation time, by the API — it is
not something `influx backup`/`influx restore` hands back to a human or to
Grafana in usable form. The only readable copy of a new token's secret is
the local file this script writes under `secrets/`.

Actual recoverability therefore requires two things, neither of which exists
yet for this task since `--apply` has not run:

1. **Off-host export** of the `secrets/*.json` credential files (the daily
   encrypted checkpoint process in
   [recovery and continuity](recovery-and-continuity-2026-09-11.md) is the
   right mechanism, but it must actually include `secrets/`, not just the
   InfluxDB backup itself).
2. **A completed restore drill** that demonstrates the exported credential
   file can actually be recovered and still authenticates — not merely an
   assumption that a future scheduled backup will happen to cover it.

Neither is claimed as done here; both remain open until verified.

> **Update 2026-09-15, after 23:45 UTC: both now exist.** (1) Off-host export:
> encrypted checkpoint `20260915T234120Z` includes both credential files
> (`credentials_included` lists all five, none skipped) and its tar is on
> Threadripper with a matching SHA-256. The run that produced it still failed
> afterwards at the MQTT stage, so `latest.json` is stale and the scheduled
> job is not yet completing unattended; the export exists, the schedule is
> not yet proven. (2) Restore drill: `scripts/verify-credential-restore.py`
> restored both files from that checkpoint in an isolated container and both
> tokens authenticated (`probe_ok: true`). Caveat: the drill used the PC copy
> and the PC restic key; the Threadripper key
> `/etc/influxdb-standby/backup-password` is documented from 2026-09-11 and its
> match to the current key is inferred, not observed. Isolated recovery is
> proven; a restore into production has not been exercised. Details in
> [Post-deploy evidence, 2026-09-15](#post-deploy-evidence-2026-09-15).
> *[2026-09-16: the Threadripper-key match is now observed by the completed
> off-host-key drill and the scheduled job succeeded in a controlled run; a
> restore into production is still not exercised. See Closeout, items 2 and 3.]*

## Remaining uncertainty for coordinator review

- Confirm 30-day retention and that Threadripper's collector write cadence
  (per the monitoring plan) won't need a shorter/longer window before first
  measuring actual daily growth.
- `iot-telegraf` was observed mid-restart during this session's discovery
  (unrelated to this bucket work) — worth a look by whoever owns that pipeline.
  *(2026-09-16: a symptom of `iot-mosquitto` being stopped since 2026-09-15 05:07 UTC;
  see [Reliability pass](#reliability-pass-2026-09-16), item 1.)*
- `--apply` has not been run; no bucket, token or credential file exists yet.
  *(Superseded 2026-09-15: applied; see Post-deploy evidence, item 1.)*
- Off-host export of `secrets/` and a completed restore drill for it are
  still outstanding (see above) — do not treat the new credential as durably
  recoverable until both are done. *(Superseded 2026-09-15: both done, with
  the MQTT-stage and restic-key caveats stated above.)*

## Handoff

- **Task ID / UTC:** `threadripper-monitor-plan-20260915` (bucket-provisioning
  sub-task), 2026-09-15.
- **Owner / client / coordinator:** worker
  `claude-sonnet-infra-provision-consolidated-20260915` (Claude Sonnet 5);
  coordinator Codex.
- **Objective / accepted scope:** implement and review-harden idempotent
  provisioning of the `infra` bucket, its Threadripper write-only token, and
  a consolidated Grafana read-only token, per coordinator's approved design
  (option B, no revocation). No live apply, no Grafana `.env` change, no
  deployment, no commits — all owned by this task's bounded contract.
- **Repository / branch:** `iot-backend`, `main`, no commits made.
- **Owned paths / claims:** `tools/provision_infra.py`,
  `tests/test_provision_infra.py`, `docs/infra-monitoring-2026-09-15.md`,
  claimed via `~/.agents/tools/coordinate.py`.
- **Changes (accepted, implemented, not yet applied):**
  - Consolidated (option B) Grafana credential design implemented in
    `tools/provision_infra.py`, replacing the earlier additive (option A)
    draft.
  - Idempotence hardened: exact-scope check, local-credential-file check
    keyed by auth ID, and a harmless authenticated probe, all required
    before any existing token is treated as already provisioned.
  - Preflight-before-create, atomic mode-0600 writes relying on `secrets/`'s
    inherited ACL on Windows, and persist-before-validate ordering so a
    live-created token's only secret copy survives a later validation
    failure.
  - `org_id`/`bucket_id` format validation before any shell interpolation.
  - Off-host-recoverability overclaim in this doc corrected.
- **Validation:** `python -m unittest tests.test_provision_infra` (53
  tests, passing); one real dry run (`python tools/provision_infra.py`, no
  `--apply`) against the live `iot-influxdb` container, read-only, no
  mutation observed.
- **Live effects:** none. No bucket, token, or `secrets/` file created.
  *(As of the original handoff; superseded 2026-09-15 by Post-deploy evidence.)*
- **Blockers / next bounded action:** none technical. Next action belongs to
  the coordinator/Grafana owner: (1) decide when to run `--apply` here, (2)
  once applied, consume `secrets/grafana-infra-token.json` in Grafana's own
  `.env`/provisioning workflow while preserving the existing datasource UID,
  and (3) schedule the off-host export + restore drill described above
  before treating the new credential as durably recoverable.
- **Authorization still required:** running `--apply` (out of scope for this
  task); the Grafana `.env` change itself (owned by that repo/coordinator).
