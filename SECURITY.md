# Security policy

## Reporting a vulnerability

Report it privately through GitHub:
[Report a vulnerability](https://github.com/InsaneCoder789/InterviewOps/security/advisories/new),
also available from the repository's **Security** tab.

Do not put vulnerability details in a public issue or pull request. If private
reporting is unavailable, open an issue that only asks the maintainer to enable a
private channel.

Please include:

- the affected file, endpoint or setting
- steps to reproduce, using local test data
- the impact you expect
- the commit you tested

## Supported versions

There are no releases yet. Fixes are made on the default branch.

## Scope

In scope: the code and configuration in this repository, for example
authentication, access to another user's data, ways around the booking rules and
leaks of sensitive data into logs.

There is no hosted instance run by this project. Do not test against systems you
do not own or have permission to test.

## Known limitations

These are documented already and do not need a private report:

- API tokens do not expire.
- Sign-up and login throttling is counted per web process.
- Email addresses are not verified, and there is no password reset.
- In debug mode, the default console email backend prints messages, including
  recipient addresses, to the worker output.
- The Django admin login page has no rate limit. The admin is off outside debug
  mode unless `ENABLE_ADMIN` is set.

The full list is in the [README](README.md#known-limits).
