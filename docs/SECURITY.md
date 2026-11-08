# Security notes

## Threat model

The package has no network access and no runtime dependencies. Its I/O is limited to reading CSV files, one render profile snapshot, and build folders, all inside fixed roots.

### Defended

- **Path traversal.** CSV paths are resolved and must stay inside `Saved/Profiling/CSV` and end in `.csv`. Build folders and cook logs must stay inside the project directory. Paths that resolve through a symbolic link to somewhere outside the root are rejected. Violations raise `path_not_allowed`.
- **Read-only build walks.** `build_size_report` never writes. It skips symbolic links (`followlinks` is off) and counts only regular files, using `lstat`.
- **Oversized input.** CSV files are checked against a byte limit before reading, and parsing stops at a row limit. Both raise `limit_exceeded`. The render profile file is read up to 65536 bytes; a larger file is ignored. The profile name is cut to 100 characters. The cook log is read up to a byte limit and truncated with a warning.
- **Hostile text.** Parsing never raises anything except `PerfError`. The job id is shortened to 60 characters in error messages, and messages are capped at 200 characters.
- **Console injection.** The adapter sends only two fixed commands, `csvprofile start` and `csvprofile stop`. No caller-supplied text reaches the console.
- **Unsafe deserialization.** The code uses `json.loads` for the render profile only and never uses `eval`, `exec` or pickle.
- **Capture overlap.** Only one capture can run at a time, and the job registry is protected by a lock.

### Not defended

- **Authorization.** Anyone able to call the adapter inside the editor can start a capture and read reports. The package has no authentication or per-user policy.
- **Symlink races.** The path check and the later read are separate steps, so a file could be swapped between them on a shared machine.
- **Resource use inside limits.** A CSV close to the size and row limits uses memory in proportion to its size. Build walks are bounded by a file-count limit, but very large trees are still scanned.
- **Editor trust.** The package trusts the `unreal` object it is given. It cannot protect against a compromised editor.
- **Estimates.** `estimated_zip_bytes` is a heuristic and must not be used as a measured archive size.

## Supply chain

There are no runtime dependencies. The only development dependency named in the specification is hypothesis. The repository's automated checks (lint, type check, security linting, secret scanning) are defined by the factory tooling; their results are not reported in this document.

## Publishing

Release publishing is intended for PyPI through trusted publishing (OIDC). No long-lived token is stored in the repository.

To report a vulnerability, see [SECURITY.md](../SECURITY.md).
