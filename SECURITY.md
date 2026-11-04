# Security Policy

## Supported Versions

Security fixes are prioritized for the latest published release and the
active `develop` branch. Older releases are not guaranteed to receive fixes.

| Version                  | Supported          |
| ------------------------ | ------------------ |
| Latest published release | :white_check_mark: |
| `develop`                | :white_check_mark: |
| Older releases           | :x:                |

## Reporting a Vulnerability

If you discover a potential security vulnerability in Global-Data-Finance,
please report it privately by email to
`estraliotojordan@gmail.com`.

Do not open a public GitHub Issue, Discussion, or Pull Request for a security
vulnerability. This is especially important for reports involving path
traversal, downloaded-file validation, archive extraction, data exposure, or
credential handling.

### What to Include

Please provide enough context to reproduce and assess the report:

1. A clear description of the vulnerability and its potential impact.
2. Affected package versions, branches, public APIs, or source areas.
3. Minimal reproduction steps or a safe proof of concept.
4. Relevant Python, operating-system, and input-file details.
5. Confirmation that the report contains no real credentials, tokens, private
   keys, or other sensitive data.

Do not include secrets or personal data in the report. Redact logs and sample
files before sending them.

## Coordinated Disclosure

We follow coordinated vulnerability disclosure. The maintainers will review
the report and coordinate a fix or mitigation before public disclosure when
appropriate. We do not promise a fixed response-time SLA.

Credit can be given to the reporter in the release notes or security advisory
if the reporter wishes to be identified.

## General Support

For questions, bug reports, and feature suggestions that are not security
issues, use the [GitHub issue tracker](https://github.com/jordanestralioto/Global-Data-Finance/issues)
or consult the [documentation](docs/index.en.md).
