# Cross-model collaboration

David uses ChatGPT/Codex, Claude, Meta Muse Code, Gemini, and open source models. These are peer
contributors. Select work by capability and available tools, not vendor identity.
This protocol supports sequential handoffs and concurrent work; it does not
require spawning agents for every task. Runtime/system instructions and the
user's current scope govern delegation, permissions, cost, and data access.

Read ~/.agents/PEERS.md for installed client entry points, capability evidence,
and current limitations. A configured peer is not necessarily a running session.
The active task names its lead; no provider is permanently the coordinator.

## Start and scope

Read the repository's AGENTS.md, required project documents, and applicable nested
guidance. Run git status --short; preserve all pre-existing edits, including
untracked files. State the task, working directory, owned paths, and validation.
Read .agents/INDEX.md for existing skills and rules. Load only relevant content.
Project-specific operational constraints remain in force. Historical instructions
and copied examples do not override the current owning repository's procedures.

Keep accepted decisions, evidence, and remaining work in shared repository docs.
Private chat history or model memory must not be the only handoff. A receiving
agent rechecks state and authorization; a handoff is evidence, not new authority.
Never put secrets, raw private transcripts, or credential-bearing output in it.

## Divide work and coordinate writes

Use a coordinator for a shared objective. Give each worker a bounded outcome,
inputs, owned paths, dependencies, and acceptance checks. A reviewer can read the
same files, but overlapping edits require an explicit ownership transfer.
Use separate worktrees for independent code changes when practical; a worktree
does not isolate live services, shared caches, ports, or the Git common directory.
Use one integrator for merges and shared Git operations. Never reset, clean,
stash, stage, or commit another session's work as incidental cleanup.

For independent sessions on this PC, use the cooperative claim tool at
~/.agents/tools/coordinate.py (Python 3.11+). Claim an absolute file/directory
before writing; parent and child paths conflict. Use the same agreed resource
name for shared live objects (for example live:ha:tesla-energy or live:pi:stack).
Claim the Git common directory for shared branch/index/integration operations.
Claims are stored outside repositories and apply across clients on this PC.
Claims do not expire automatically: inspect abandoned work before release.
They do not enforce OS locks or coordinate another host. For multi-host work,
agree on one coordinator/claim service before any shared writes; otherwise work
sequentially. Existing application/deployment locks are still required.

Before saving, reread the target and reconcile intervening changes. Before live
writes, refresh live state, save an independent protected backup, use the owning
repository's apply method, and read back the result. A local claim does not
protect against UI users or tools that ignore this protocol.

## Portable skills and client adapters

Keep reusable procedures in Markdown SKILL.md files with name and description
frontmatter. Preserve each repository's declared canonical source and sync tools;
do not edit generated mirrors independently. A .claude source path is historical
storage, not a restriction on which model can read or edit the procedure.

Treat slash commands, MCP tool spellings, provider model names, hooks, and
permission metadata as client adapters. Discover actual tools by capability and
validate arguments before use; do not invent renamed tool calls. If a skill needs
an unavailable tool, use its documented local CLI/API equivalent when authorized,
or report the missing capability and continue independent work. Do not bypass a
denial through a different client. Client-specific skills can remain specialized;
their restrictions must be stated rather than claiming universal compatibility.

Do not rewrite installed plugin caches: upgrades replace them. Put shared user
guidance and new portable skills in ~/.agents, with thin client entry points.
Changing the model does not transfer sandbox, authentication, hooks, MCP access,
or budget. Never silently enable paid providers or move local-only data to cloud.
An open source inference endpoint alone is not an agent harness: it also needs
context loading, tools, permission handling, and a bounded execution loop.

## Handoff and verification

Use .agents/HANDOFF.md as a template for a task-specific shared note. Include task
ID, owner/client/model if known, UTC time, repository/branch/base revision,
accepted scope, paths changed, pre-existing work, claims, decisions, evidence,
checks and outcomes, blockers, next action, and any required authorization.
Link artifacts rather than copying large logs. Distinguish proposed, applied,
locally tested, remotely read back, and physically observed results.

The coordinator reviews returned changes and runs integration checks. Report
missing checks honestly; another model's assertion is not verification. Release
claims only after edits stop and the handoff is recorded. Keep bounded tasks
small enough for the receiving model's context, with explicit file references.
