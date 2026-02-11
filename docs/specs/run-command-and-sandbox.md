# RunCommandTool and Safe Mode (Bubblewrap): Specification

This document describes **RunCommandTool** (agent tool for executing shell commands) and how **safe** mode works via **Bubblewrap (bwrap)** on Linux. Unsafe mode uses the OS subprocess directly and works on all platforms.

---

## 1. What this is

### RunCommandTool

**RunCommandTool** runs shell commands (e.g. `ls -la`, `python script.py`). Two modes:

- **Unsafe (default)**: The command runs via the OS (asyncio subprocess). You can set **root_path** so the process uses that directory as cwd and path-like arguments cannot escape outside it. Works on Windows, macOS, Linux.
- **Safe**: The command runs inside **Bubblewrap (bwrap)** sandbox: minimal filesystem view (read-only /usr, workspace bind), namespaces, no network by default. **Linux only**; requires `bwrap` to be installed. If `bwrap` is not found, the tool returns an error with an installation link.

So: **safe = bwrap isolation (Linux); unsafe = OS subprocess (all platforms).**

---

## 2. How it works

### RunCommandTool flow

1. **Config**: In the global `tools:` section or per-agent: `root_path`, `mode` (`"unsafe"` or `"safe"`), `timeout_seconds`. Default mode is **unsafe**.
2. **LLM**: The agent passes a `command` string (and `reasoning`) to the tool.
3. **Unsafe**: The tool resolves `root_path` (if set), validates path-like tokens, then runs `sh -c "<command>"` with `cwd=root_path` and a timeout. Returns formatted stdout, stderr, return code.
4. **Safe**: The tool checks that `bwrap` is available (e.g. `bwrap --version` or `which bwrap`). If not, returns an error with link to [Bubblewrap installation](https://github.com/containers/bubblewrap#installation). If available, runs the command via `bwrap` with minimal default settings (see below) and a timeout. Returns formatted stdout, stderr, return code.

### Safe mode: minimal default settings (bwrap)

Safe mode uses a minimal but useful bwrap setup so the sandbox works out of the box:

- **Filesystem**: Read-only bind of `/usr`; symlinks for `/bin`, `/lib`, `/lib64`; `--proc /proc`, `--dev /dev`; a writable **workspace** directory bound as `/workspace` (from `root_path` if set, else a temporary directory or current working directory).
- **Execution**: Process runs with `--chdir /workspace`, `--unshare-all`, `--die-with-parent`; command is run as `/bin/sh -c "<command>"`.
- **Timeout**: Enforced by the tool (subprocess timeout) after `timeout_seconds`.

This gives isolation (namespaces, limited filesystem) without extra configuration. Optionally, future config could expose more bwrap options (e.g. extra read-only binds).

---

## 3. Configuration reference

All parameters are optional. Set in the global `tools:` section or per-agent.

| Parameter          | Type     | Default     | Description |
|--------------------|----------|-------------|-------------|
| `root_path`        | str      | None        | Directory for cwd (unsafe) or bwrap workspace (safe). In safe mode, this directory is bound as `/workspace` inside the sandbox. |
| `mode`             | str      | `"unsafe"`  | `"safe"` or `"unsafe"`. Safe uses bwrap (Linux only); unsafe uses local subprocess. |
| `timeout_seconds`  | int      | 60          | Max execution time in seconds. |

Tool parameters (from the LLM / schema): `reasoning` (str), `command` (str, full command line).

Example (unsafe):

```yaml
tools:
  run_command_tool:
    root_path: "/tmp/agent_workspace"
    mode: "unsafe"
    timeout_seconds: 120
```

Example (safe, Linux with bwrap installed):

```yaml
tools:
  run_command_tool:
    root_path: "/tmp/agent_workspace"
    mode: "safe"
    timeout_seconds: 60
```

### Installing Bubblewrap (for safe mode)

Safe mode requires **bwrap** on the system. If it is not installed, the tool returns an error message with a link to installation instructions.

- **Installation**: See [Bubblewrap - Installation](https://github.com/containers/bubblewrap#installation). On Debian/Ubuntu: `apt install bubblewrap`. On Fedora: `dnf install bubblewrap`. On Arch: `pacman -S bubblewrap`.
- **Docker**: When using the project Docker image, bubblewrap is installed via `apt` in the image so safe mode works without extra steps.

---

## 4. Analogues and alternatives

### Unsafe mode (OS)

Unsafe mode uses the OS subprocess and optional **root_path**; works on all platforms. Use when you only need a directory boundary or when bwrap is not available (e.g. Windows, macOS).

### Bubblewrap (safe mode)

[bubblewrap](https://github.com/containers/bubblewrap) is a lightweight unprivileged sandbox using Linux namespaces and bind mounts. It is used by Flatpak and others. Safe mode builds a minimal environment so that commands run in isolation with a single writable workspace.

---

## 5. Security notes

- **Unsafe**: Runs as the same user as the agent. Path validation limits access to `root_path`; use timeout to avoid hanging.
- **Safe**: Uses bwrap for namespace and filesystem isolation. The sandbox is not a full security boundary; use as a mitigation layer. Ensure `root_path` points to a dedicated workspace, not a sensitive directory.

---

## 6. Summary

| Item | Description |
|------|-------------|
| **RunCommandTool** | Runs shell commands; **unsafe** = OS subprocess (all platforms); **safe** = bwrap sandbox (Linux, requires bwrap). |
| **bwrap** | Must be installed for safe mode. Install: [Bubblewrap - Installation](https://github.com/containers/bubblewrap#installation). |
| **Minimal defaults** | Safe mode uses a minimal bwrap setup: ro-bind /usr, workspace as /workspace, unshare-all, timeout. |
