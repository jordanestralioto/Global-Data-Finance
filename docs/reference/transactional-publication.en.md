# Transactional publication

The internal `macro_infra/transactional_publication/` infrastructure publishes
CVM and B3 artifacts as a recoverable batch. Source owners remain responsible
for validating content, schemas, and counts before commit. Concurrent readers
may observe individual replacements during commit; recovery delivers the old
or new batch according to the durable journal.

## Lock acquisition and recovery

Acquisition and removal of `.globaldatafinance-transaction.lock` use an
operating-system guard released when its descriptor closes or the process
terminates:

- POSIX locks the destination directory descriptor.
- Windows uses the empty, private, persistent
  `.globaldatafinance-publication.guard` file. It is not transaction residue
  and must stay in place while writers may run: contenders must lock the same
  file.

The guard protects the window before `owner.json` is persisted and serializes
recovery attempts. After initialization, the record identifies hostname, PID,
and `process_started_at`, the process start returned by
`psutil.Process.create_time()`. This timestamp can change with system clock
adjustments. A live PID with a different start time may indicate PID reuse
or a clock change; this difference cannot authorize recovery. Any live PID,
permission failures, invalid identities, and locks from another host block
recovery. A lock with an identified owner is recovered automatically only
when its PID no longer exists on the same host and process namespace.
A private lock without an owner is recovered automatically only when empty
or containing private `owner.json` temporaries.
Unrecognized contents, aliases, and unsafe permissions are preserved with an
explicit error.

PID queries use `psutil.Process.is_running()`, without sending signals or
Windows console events. Permission failures during the query prevent recovery
and preserve their diagnostic cause.

### Manual recovery and containers

An older lock without `process_started_at` remains recoverable when its PID
does not exist; a live PID retains the conservative behavior. PIDs from
different containers do not identify the same process. A PID absent in the
current container, file age, or a changed hostname cannot prove that the
previous writer exited. Shared destinations require identifiable hosts and
writers in the same process namespace when they use the same hostname.

To resume after an interruption:

1. Stop downloads, extractions, and other destination writers, including on
   other hosts or containers. Confirm in the original environment that the
   owning process exited; otherwise preserve the destination and use a new
   directory.
2. Preserve a complete destination copy, including ZIPs, Parquets,
   `.cvm-write-lock`, `.globaldatafinance-transaction.lock`, manifests, and
   staging. Inspect `owner.json` without changing PID, hostname, or timestamps.
3. CVM's `.cvm-write-lock` is a separate outer lock requiring manual release
   after this confirmation. If it contains only a private, regular
   `owner.json`, remove that file and then the empty directory. Additional
   contents, links, or unknown ownership require inspection; do not delete
   the tree recursively.
4. On the same host and namespace, run the facade again in the same
   destination. A transaction lock is recovered automatically only when its
   recorded PID no longer exists; journals determine rollback or completion
   before the new publication starts. A live PID still blocks recovery even
   with a different start time. Preserve logs if recovery fails.
5. For a transaction lock from another host, any still-live PID (including
   a reused PID), or an unverifiable identity, regenerate into a new directory
   using the preserved sources and check the result before switching consumers. This
   version provides neither automatic cross-host takeover nor a forced
   recovery command.

Do not delete journals, backups, staging, or the Windows guard file to
unblock publication: doing so can remove the authority required to recover
the batch. Checking the facade result remains mandatory.

## Staging and manifests

New transactions create staging inside the private lock, on the same
filesystem as outputs. Manifest temporaries stay inside staging. Crashes
before the first journal or external JSON promotion leave residues inside a
tree with ownership established by the lock.

The private journal remains the authority for artifact recovery; the external
JSON serves discovery. Directory and artifact identities, SHA-256, and
ownership checks prevent the external record from authorizing caller-file
deletion. Outputs changed outside the transaction are preserved. Cleanup
removes children before `owner.json`, retaining the record if staging removal
is interrupted.

## Compatibility and limits

Valid journals from the previous layout, with staging directly in the
destination, remain recoverable, including when the external manifest is
missing. Older directories and temporaries without verifiable authority
remain preserved for explicit inspection; their prefixes cannot authorize
deletion.

The guard requires filesystem support for native locking. The boundary still
requires filesystem isolation and excludes hostile concurrent writers and
arbitrary process access under the same UID. Publication recovery also does
not replace the inspection required by the CVM flow's outer `.cvm-write-lock`.

File data is synced before publication. On Windows, this uses write access
as required by the CRT. Directory `fsync` on that platform is
explicitly reported as unsupported with a warning; the flow does not attempt
to open directories through the CRT file API. On platforms supporting this
operation, permission and I/O failures still interrupt the transaction.
Recovery after process termination does not imply power-loss durability on
every filesystem.
