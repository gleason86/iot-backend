# Recovery and continuity — 2026-09-11 UTC

Production InfluxDB, Mosquitto and Telegraf remain on Ryzen. No client endpoint,
bucket retention or live collector configuration changed. Threadripper holds an
independent encrypted checkpoint and a restored, disabled InfluxDB cold standby.
Automatic promotion is not implemented. Coordination and all-host placement are
in [Threadripper's inventory](../../threadripper/docs/service-continuity-2026-09-11.md).

## Actual InfluxDB checkpoint and independent native restore

Observed image: InfluxDB 2.7.12, commit ec9dcde5d6,
`influxdb@sha256:b548ea6cdd265b4c28b305be5a93c4fc8b0d60583989598156895b80eefe29f4`.
The live Compose tag remains `influxdb:2`; do not pull/upgrade it accidentally.
`scripts/influx-recovery.py` uses the native online backup API, restores in a
disposable network-none container, checks bucket/authorization metadata and Flux
queries, and restarts the restored instance. No production writer is stopped.
The first full successful run at 07:09 UTC took 4.688 seconds for capture and
19.078 seconds for restore/query. An initial test lacked an explicit organization
for CLI listing; that test failed safely and its isolated container was removed.

`scripts/encrypt-checkpoint.py` adds backend environment, MQTT password file and
operator credential, encrypts the checkpoint with Restic, checks every pack,
restores every file and compares the restored tree. The encrypted snapshot
`7bd6662f1ec9735223c9ff0366d963a96cfccbe5ea554447edc6249f2d7b210e` is on PC
`D:/Backups/iot-backend/20260911/repository` and independent Threadripper
`/srv/iot-recovery/repository`. Root-only server key:
`/etc/influxdb-standby/backup-password`. PC keys are in ignored `secrets/`:
`influx-restic-password`, `influx-operator-token`. Never put key contents in Git.

Threadripper's `playbooks/iot-standby.yml` imports this repo's `roles/standby`.
The native executables were extracted from the pinned image and verified:

| Binary | SHA-256 |
|---|---|
| influx | d92421584132219500587f364794249dde338fccd0ac8e4a06dfdd5d5997c89e |
| influxd | c7b2b83976f5f5971a3fee323f2f0baf6a3f9b0f692a1efadf8756da90b8766f |

Runtime `/opt/influxdb-2.7.12`; private state `/srv/influxdb-standby`; service
`influxdb-standby`, **stopped and disabled** after the drill. It binds only
127.0.0.1:8086 and systemd blocks non-loopback network access. Limits: 2 GiB RAM,
zero swap, two CPU equivalents, 256 tasks. It is a recovery target, not an active
replica. Existing client routing remains unchanged.

`playbooks/restore-checkpoint.yml` checked all encrypted packs on Threadripper,
restored to a new private directory, initialized a scratch server with the original
operator credential, restored full metadata/data, queried with the recovered
Grafana read token, restarted, queried again and stopped the service in `always`.
An initial CLI attempt tried to resolve `home` before its metadata was restored;
the corrected procedure resolves the organization afterward. `--resume-setup`
can only resume an untouched `restore-drill` organization; it cannot overwrite a
populated home server. Normal execution refuses an initialized target.

At 07:24:45 UTC, native restore/query took 17.647 seconds; post-restart queries
took 9.305 seconds. Both runs preserved bucket IDs, retention, seven original
authorizations, and these checkpoint field-row counts:

| Bucket | ID | Retention | Restored rows |
|---|---|---|---:|
| iot | dc846c7b25ee1436 | unlimited | 11,023,385 |
| network | 57497837fc976b6f | 90 days | 1,404,946 |
| voice_telemetry | bf46fdb9d8a893fd | unlimited | 695,855 |

The restored system buckets also match. Safe aggregate evidence is at
`/srv/iot-recovery/standby-verification.json`. This cold standby is the 07:09
checkpoint; newer backup archives are not silently restored into it.

## Daily InfluxDB and MQTT recovery

Windows task **IoT Backend Verified Encrypted Recovery** runs at 03:15 Pacific,
using `scripts/daily-recovery.py`; install with `scripts/install-recovery-task.ps1`.
It requires David logged in, Docker Desktop and existing SSH key access. It performs
online capture, native isolated restore, encryption and file-level restore, then
copies checksum-verified ciphertext to `/home/david/iot-checkpoints/` on Threadripper.
It does not refresh/promote the standby. Recovered credentials are in the encrypted
checkpoint. The monitor identity added later is included in subsequent snapshots.

The expanded job returned Windows result 0 at 07:53 UTC. Latest verified Influx
copy: `/home/david/iot-checkpoints/20260911T075221Z.tar`, SHA-256
`5210ac7f0587ee0bcbf470610cf745186c82f29c3ba90b59011c558d790100eb`.
Latest MQTT copy: `/home/david/iot-checkpoints/mqtt-20260911T075221Z.tar`, SHA-256
`0cdeb4f57fcedb764a7e169492dedb3ccc7a0929dc64115207654ebb706e9104`.
The machine-readable current result is `D:/Backups/iot-backend/latest.json`.
One earlier unattended SSH transfer finished remotely but its client hung;
stdin is now closed and SSH keepalives/timeouts are bounded. The next full job passed.

No pruning or snapshot deletion is enabled. PC storage budget: 20 GiB, with
20 GiB free reserve. Independent checkpoint budget: 10 GiB, with 20 GiB OS reserve.
Exhaustion fails the job visibly in Task Scheduler. A 24-hour RPO is proposed only
while PC/login/Docker/network conditions permit the daily run. No off-site copy
or simultaneous-PC/server-loss protection is established.

`scripts/mqtt-recovery.py` sends SIGUSR1 to flush the production persistence file,
compares its hash around the copy, then restores into a network-none broker without
live volumes or client connections. At 07:39 UTC it accepted the original MQTT
credentials, persisted a synthetic retained message, restarted and returned that
message. The original checkpoint was encrypted/restored identically; snapshot
`f925c8687b7194308a5033d69792275c1f80cf83f485ffac4e0bf0fdeb362bce` also passed
all-pack checking on Threadripper. Production clients were not disconnected.
This does not establish end-to-end sensor QoS or replay of previously lost samples.
The separate Mosquitto file log was 10.6 MiB; it remains unbounded by Docker stdout
rotation and should be addressed in a reviewed broker configuration change.

## Failure drills and their limits

`python tests/continuity_drill.py` uses three synthetic Influx instances on an
internal Docker network, with no published ports or real credentials. At 07:35 UTC:

- Initial replication took 0.297 seconds. A pre-stream record was absent on the
  replica, proving no historical backfill in this fixture.
- Disconnecting the standby produced a durable queue (217 bytes, 141 pending).
  The queue survived SIGKILL of the source. It remained idle after restart without
  new writes (also observed over 180 seconds in an earlier attempt); an explicit
  idempotent replay of a fixture point resumed delivery in 0.328 seconds.
- Deletion on the source did not delete the replica's point. Queries read actual
  field rows; tag-index-only queries were unsuitable for proving deletion.
- The test rejected stale standby contents, positively stopped the old writer,
  admitted one synthetic writer, isolated the returning old primary, made a fresh
  full backup, restored a new failback instance, stopped the current writer and
  resumed there. Final fixture IDs 2–14 appeared once each.

This is explicit operator fencing inside a test, not a distributed lease, witness
or production failover controller. No physical host or household network failed.

`python tests/buffer_disk_drill.py` at 07:43 UTC used each actual deployed Telegraf
image with a synthetic three-metric buffer and unavailable output. Both 1.29.5
and 1.32.3 overflowed and restarted with an empty queue after SIGKILL. The live
10,000/20,000 limits therefore must not be described as durable storage.

The same test filled an isolated InfluxDB 64 MiB tmpfs filesystem until ENOSPC.
Influx rejected the write. Freeing space alone retained a failed-shard state;
restarting only influxd, preserving that filesystem, allowed an idempotent retry
and exactly one final row. This exercises real ENOSPC in a disposable filesystem,
not a full production SSD or physical power loss.

At 08:11:16 UTC, `python tests/persistent_buffer_drill.py` tested experimental
Telegraf 1.32.3 disk buffering in a separate disposable named volume. After
SIGKILL and complete collector-container replacement, the empty-source replacement
replayed all ten fixture field rows in 3.016 seconds. The queue used 26,992 bytes.
Ten rows survived despite `metric_buffer_limit=3`; this setting does not provide
the required disk-space bound. Fixed timestamps let Influx deduplicate repeated
input samples, so transport exactly-once delivery is not proven. The initial
fixture could not attach an internal network while Docker's `none` network was
still attached; the corrected test detaches it first and all resources were removed.
No production buffer setting changed. Physical power loss, bounded disk-full
behavior, cross-host queue transfer and transactional event-baseline replay remain
unproven. See the [versioned buffer configuration](https://raw.githubusercontent.com/influxdata/telegraf/v1.32.3/docs/CONFIGURATION.md).

Official references: [full restore](https://docs.influxdata.com/influxdb/v2/admin/backup-restore/restore/),
[replication semantics](https://docs.influxdata.com/influxdb/v2/write-data/replication/replicate-data/),
[2.7.12 implementation](https://raw.githubusercontent.com/influxdata/influxdb/v2.7.12/replications/service.go),
[1.29.5 MQTT session behavior](https://raw.githubusercontent.com/influxdata/telegraf/v1.29.5/plugins/inputs/mqtt_consumer/README.md).
Replication does not synchronize tokens, retention, deletions or historical state;
do not construct a two-writer cluster by listing two URLs.

## Independent read-only monitoring

`roles/monitor`, imported by Threadripper's `playbooks/continuity-monitor.yml`, runs
once per minute on Threadripper. It reads only Influx watermarks for HA history and
seven network measurements, with a dedicated read-only iot/network token. It
retrieves no household measurement values, follows no redirects, sends no messages
and never promotes services. Three consecutive bad/good observations are needed
for failure/recovery. The first query had mixed-field grouping errors; the corrected
query removes values before grouping and passed against the live backend.

At 07:55:36 UTC, `/srv/continuity-monitor/health.json` was healthy with four
consecutive good samples and no stale producer. NTP synchronization is confirmed.
Config/key: root `/etc/continuity-monitor/config.json` (group-readable only by its
dedicated service user), independent PC `secrets/continuity-monitor.json`.
128 MiB RAM, quarter CPU, 30-second deadline and bounded 20 MiB private journal.
It is independent detection/state, not independent notification delivery. Local
failure/recovery transitions have two passing regression tests. Do not interpret
a quiet individual HA entity as a dead controller; the monitored W stream is a
producer-history signal. Physical outage/contact delivery remains untested.

## Operator recovery and rollback

Keep the former primary fenced before any promotion; inspect the **latest**
verified archive, not merely the preloaded cold standby. Recover the key separately,
run Restic all-pack checks, restore to a fresh private directory and use the pinned
native/image version. Verify identities, retention, record freshness and actual
consumer queries before Networking changes any endpoint. Failback requires a
fresh export from the current writer and the same one-writer checks.

Disable the named Windows task to stop backups. Stop/disable
`continuity-monitor.timer` and its service to stop checks. Leave
`influxdb-standby` disabled; preserve its data and all backup/credential locations.
The new monitor token can be revoked by its description after the monitor is
disabled; no existing token should be removed. No production rollback is needed
for the restore fixtures because they never replaced production data or routes.

Disposable Ansible syntax/render tests, two monitor tests, actual native/container
restores and the above synthetic failure drills passed. Physical fencing, attended
host-loss tests, alert recipient selection, durable collector migration and off-site
custody remain open. These results do not establish automatic high availability.
