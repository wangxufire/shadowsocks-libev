# Contributing to shadowsocks-c

Bug reports, fixes, tests, and documentation improvements are welcome. Please
follow our [Code of Conduct](CODE_OF_CONDUCT.md) in all project spaces.

## Issues and proposals

Search existing issues and pull requests before opening a new one. For a bug,
include the version or commit, operating system, build options, steps to reproduce,
and expected and actual behavior. Include relevant logs and a minimal
configuration with passwords and other private information removed.

For substantial changes, open an issue first to discuss the problem, proposed
approach, and compatibility impact.

## Development setup

Fork the repository, clone your fork, and create a descriptive branch from the
current `master`, such as `fix/dns-timeout` or `feature/new-option`. Do not commit
directly to `master`.

The default bundled build requires a C11 compiler, CMake 3.20 or newer, and Make
or Ninja. Pinned dependency sources are included; configuration and compilation
do not require network access or Git submodules. Install Python 3 for integration
tests and Bash for shell tests.

Run these commands from the repository root:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build -LE memcheck --output-on-failure --no-tests=error
bash tests/test_ss_setup.sh
python3 tests/stress_test.py --bin build/bin/ --size 10
```

Built programs are in `build/bin/`. See the [README](README.md#build-from-source-cmake)
for build options and [modernization notes](docs/modernization.md) for portability
and compatibility requirements.

## Style and validation

Match the surrounding code style and keep changes focused. The C formatting
configuration is [`.uncrustify.cfg`](.uncrustify.cfg); avoid unrelated formatting
changes and edits to vendored code. Add regression coverage for behavior changes
and update documentation when commands, configuration, or public behavior change.

Before pushing, run the build and tests above and the CI lint commands below.
Install `actionlint` 1.7.12 and `ruff` 0.15.6, the versions currently pinned in
[the test workflow](.github/workflows/tests.yml).

```sh
actionlint -shellcheck= -pyflakes=
ruff check --select E9,F63,F7,F82 tests scripts
git diff --check
```

Transport and protocol changes should also pass independent TCP/UDP
interoperability tests. With the shadowsocks-rust `sslocal` and `ssserver`
executables on `PATH`, run:

```sh
SS_REQUIRE_INTEROP=1 SS_BIN_DIR=build/bin bash tests/test_interop_rust.sh
```

The required mode fails when prerequisites are missing; optional local runs may
skip interoperability tests. Report skips explicitly. CI also covers sanitizers,
Linux memory checks, static analysis, packaging, and additional platforms; consult
[the workflows](.github/workflows) for checks relevant to your change.

Preserve existing CLI, configuration, protocol, and public API compatibility
unless a change has been discussed. For bundled dependency updates, follow
[the update procedure](third_party/README.md) and preserve upstream licenses and
notices.

## Pull requests

Open your pull request against `master`. Explain the problem, what changes for
users, and how you validated the result. Link related issues and describe any
limitations or platform-specific behavior. Keep unrelated work in separate pull
requests and exclude generated build output, credentials, and local configuration.

Respond to review feedback and keep the branch current with `master`. Maintainers
will review the implementation and relevant CI results before merging.
