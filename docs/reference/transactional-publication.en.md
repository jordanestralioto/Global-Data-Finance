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
recovery attempts. After initialization, the record still rejects live PIDs
and locks from another host. A private lock without an owner is recovered
automatically only when empty or containing private `owner.json` temporaries.
Unrecognized contents, aliases, and unsafe permissions are preserved with an
explicit error.

PID queries use `psutil.Process.is_running()`, without sending signals or
Windows console events. Permission failures during the query prevent recovery
and preserve their diagnostic cause.

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
