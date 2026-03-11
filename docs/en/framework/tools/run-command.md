# RunCommandTool and Safe Mode (Bubblewrap)

This document describes **RunCommandTool** (agent tool for executing shell commands) and how **safe** mode works via **Bubblewrap (bwrap)** on Linux. Unsafe mode uses the OS subprocess directly and works on all platforms.

---

## 1. What this is

### RunCommandTool

**RunCommandTool** runs shell commands (e.g. `ls -la`, `python script.py`). Two modes:

- **Safe (default)**: The command runs inside **Bubblewrap (bwrap)** sandbox: minimal filesystem view (read-only /usr, workspace bind), namespaces, no network by default. **Linux only**; requires `bwrap` to be installed. If `bwrap` is not found, the tool returns an error with an installation link.
- **Unsafe**: The command runs via the OS (asyncio subprocess). You can set **workspace_path** so the process uses that directory as cwd and path-like arguments cannot escape outside it. Works on Windows, macOS, Linux.

So: **safe (default) = bwrap isolation (Linux); unsafe = OS subprocess (all platforms).**

---

## 2. How it works

### RunCommandTool flow

1. **Config**: In the global `tools:` section or per-agent: `workspace_path` (optional), `mode` (`"safe"` or `"unsafe"`), `timeout_seconds`, `include_paths` (optional list of allowed commands/paths), `exclude_paths` (optional list of forbidden commands/paths). Default mode is **safe**. If RunCommandTool is used anywhere (global or in any agent) and `workspace_path` is not set for the effective config, the server creates a default `./workspace` directory next to `config.yaml` and uses it as the workspace.
2. **LLM**: The agent passes a `command` string (and `reasoning`) to the tool.
3. **Validation**: If `include_paths` or `exclude_paths` are set, the tool checks that the command executable and paths in arguments are allowed. Commands are matched by name (e.g. `"ls"`) or resolved path (e.g. `/usr/bin/ls`). **include_paths has priority over exclude_paths**: if a path is in both, it is allowed.
4. **Unsafe**: The tool resolves `workspace_path` (if set), validates path-like tokens, then runs `sh -c "<command>"` with `cwd=workspace_path` and a timeout. Returns formatted stdout, stderr, return code.
5. **Safe**: The tool checks that `bwrap` is available (e.g. `which bwrap`). If not, returns an error with link to [Bubblewrap installation](https://github.com/containers/bubblewrap#installation). If available:
   - If `include_paths` or `exclude_paths` are set in the tool configuration, **OverlayFS** mounts are created at **server startup** (not per-command):
     - Server checks global `tools:` and each agent's `tools` list; if RunCommandTool is used anywhere with `mode: "safe"` and `include_paths`/`exclude_paths` set, OverlayFSManager creates overlay filesystems:
       - Creates temporary directories for overlay layers (lowerdir, upperdir, workdir)
       - Mounts original directories as lower layer (read-only)
       - Creates whiteout files in upper layer for excluded binaries
       - Mounts overlay filesystems and stores mount paths
     - These mounts are reused for all command executions during server lifetime
   - At runtime, the tool uses pre-initialized OverlayFS mounts from OverlayFSManager
   - This restricts which binaries are available inside the sandbox at the filesystem level, including commands executed by scripts
   - If neither `include_paths` nor `exclude_paths` are set, uses default mounts (read-only `/usr`, etc.)
   - On server shutdown, all OverlayFS mounts are automatically unmounted and temporary directories cleaned up
   - Runs the command via `bwrap` with the configured mounts and a timeout. Returns formatted stdout, stderr, return code.

### Safe mode: minimal default settings (bwrap)

Safe mode uses a minimal but useful bwrap setup so the sandbox works out of the box:

- **Default filesystem** (when `include_paths` is not set): Read-only bind of `/usr`; symlinks for `/bin`, `/lib`, `/lib64`; `--proc /proc`, `--dev /dev`; a writable **workspace** directory bound as `/workspace` (from `workspace_path` if set, else a temporary directory or current working directory).
- **Restricted filesystem** (when `include_paths` or `exclude_paths` are set): Uses **OverlayFS** to create a filtered view of the filesystem:
  - **Initialization**: OverlayFS is initialized **once at server startup** if RunCommandTool is used with `mode: "safe"` **anywhere** (global `tools:` or any agent's `tools`). Paths (`include_paths`/`exclude_paths`) may be unset; then no overlay mounts are created but the manager is ready. If paths are set, overlay mounts are created for those directories.
  - **Lower layer**: Original directories (e.g., `/usr/bin`) mounted read-only
  - **Upper layer**: Temporary directory containing whiteout files for exclude_paths
  - **Merged layer**: OverlayFS mount combining lower and upper layers, hiding excluded files
  - For example, if `include_paths: ["ls", "cat"]` and `exclude_paths: ["rm"]`, and all are in `/usr/bin`:
    - Lower layer: `/usr/bin` (read-only, contains all binaries)
    - Upper layer: Contains whiteout file `.wh.rm` to hide `rm`
    - Merged: `/usr/bin` overlay showing `ls` and `cat` but not `rm`
  - The overlay is mounted in bwrap at the original location
  - Essential system directories (`/lib`, `/usr/lib`, `/lib64`, `/usr/lib64`) are always mounted for shared library dependencies
  - **Reuse**: Same overlay mounts are reused for all command executions during server lifetime (no per-command overhead)
  - **Cleanup**: On server shutdown, all OverlayFS mounts are automatically unmounted and temporary directories removed
  - This ensures that commands executed inside scripts (e.g. `bash script.sh` calling `rm`) are also restricted: if `rm` is hidden by whiteout, it won't be available in the sandbox
- **Execution**: Process runs with `--chdir /workspace`, `--unshare-all`, `--die-with-parent`; command is run as `/bin/sh -c "<command>"`.
- **Timeout**: Enforced by the tool (subprocess timeout) after `timeout_seconds`.

This gives isolation (namespaces, limited filesystem) without extra configuration. When `include_paths`/`exclude_paths` are used, the sandbox uses OverlayFS to restrict binaries at the filesystem level, so scripts cannot execute forbidden commands even if they try.

### OverlayFS Implementation Details

**How OverlayFS works:**

- **Lower layer** (read-only): Contains the original filesystem (e.g., `/usr/bin` with all binaries)
- **Upper layer** (writable): Contains whiteout files (`.wh.<filename>`) that hide files from the lower layer
- **Work directory**: Temporary directory used by OverlayFS for atomic operations
- **Merged mount**: The combined view where excluded files are hidden

**Whiteout files:**

- Format: Character device with major/minor number 0/0, or regular file named `.wh.<original_filename>`
- When OverlayFS encounters a whiteout, it hides the corresponding file from the lower layer
- This allows excluding specific files from a directory without excluding the entire directory

**Lifecycle Management:**

- **Server startup**: OverlayFS is initialized by `OverlayFSManager` during FastAPI `lifespan` startup phase
- **Configuration**: RunCommandTool config is taken from global `tools:` or from any agent (first candidate with `mode: "safe"` wins). If **everywhere** is `mode: "unsafe"`, overlay is **not** initialized. If **any** config (global or any agent) has `mode: "safe"`, overlay **is** initialized (include_paths/exclude_paths may be unset; then 0 mounts).
- **Initialization**: Whenever at least one safe config exists (global or per-agent)
- **Runtime**: Pre-initialized mounts are reused for all command executions (no per-command overhead)
- **Server shutdown**: All OverlayFS mounts are automatically unmounted and temporary directories cleaned up during FastAPI `lifespan` shutdown phase

**Advantages:**

- Native kernel mechanism (no SUID required)
- Fine-grained file exclusion within directories
- Works seamlessly with bwrap
- Efficient: mounts created once at startup, reused for all commands
- Automatic cleanup on server shutdown

---

## 3. Configuration reference

All parameters are optional. Set in the global `tools:` section or per-agent.

| Parameter         | Type      | Default  | Description |
|-------------------|-----------|----------|-------------|
| `workspace_path`  | str       | None     | Directory for cwd (unsafe) or bwrap workspace (safe). In safe mode, this directory is bound as `/workspace` inside the sandbox. If not set when RunCommandTool is used, the server creates a default `./workspace` directory next to `config.yaml` and uses it. |
| `mode`            | str       | `"safe"` | `"safe"` or `"unsafe"`. Safe uses bwrap (Linux only); unsafe uses local subprocess. |
| `timeout_seconds` | int       | 60       | Max execution time in seconds. |
| `include_paths`   | list[str] | None     | Allowed commands/paths. If set, only commands in this list can be executed. Commands are matched by name (e.g. `"ls"`) or full path (e.g. `"/usr/bin/ls"`). Paths in command arguments are also checked. **Has priority over exclude_paths** (same path in both is allowed). |
| `exclude_paths`   | list[str] | None     | Excluded commands/paths. If set, these are forbidden unless also in `include_paths`. |

Tool parameters (from the LLM / schema): `reasoning` (str), `command` (str, full command line).

Example (unsafe):

```yaml
tools:
  run_command_tool:
    workspace_path: "/tmp/agent_workspace"
    mode: "unsafe"
    timeout_seconds: 120
```

Example (safe, Linux with bwrap installed):

```yaml
tools:
  run_command_tool:
    workspace_path: "/tmp/agent_workspace"
    mode: "safe"
    timeout_seconds: 60
```

Example (with include_paths/exclude_paths - restrict allowed commands):

```yaml
tools:
  run_command_tool:
    workspace_path: "/tmp/agent_workspace"
    mode: "unsafe"
    timeout_seconds: 60
    include_paths:
      - "ls"
      - "cat"
      - "/usr/bin/python3"
      - "/tmp/agent_workspace"  # Allow access to workspace directory
    exclude_paths:
      - "rm"
      - "/usr/bin/rm"
```

### Installing Bubblewrap (for safe mode)

Safe mode requires **bwrap** on the system. If it is not installed, the tool returns an error message with a link to installation instructions.

- **Installation**: See [Bubblewrap - Installation](https://github.com/containers/bubblewrap#installation). On Debian/Ubuntu: `apt install bubblewrap`. On Fedora: `dnf install bubblewrap`. On Arch: `pacman -S bubblewrap`.
- **Docker**: When using the project Docker image, bubblewrap is installed via `apt` in the image so safe mode works without extra steps.

---

## 4. Analogues and alternatives

### Unsafe mode (OS)

Unsafe mode uses the OS subprocess and optional **workspace_path**; works on all platforms. Use when you only need a directory boundary or when bwrap is not available (e.g. Windows, macOS).

### Bubblewrap + OverlayFS (safe mode)

[bubblewrap](https://github.com/containers/bubblewrap) is a lightweight unprivileged sandbox using Linux namespaces and bind mounts. It is used by Flatpak and others. Safe mode combines bwrap with **OverlayFS** to provide fine-grained filesystem control:

- **bwrap** provides namespace isolation (PID, UTS, IPC, NET, MNT, USER, CGROUP, TIME)
- **OverlayFS** provides file-level exclusion through whiteout files
- This combination allows mounting directories while excluding specific files, without requiring SUID binaries

Safe mode builds a minimal environment so that commands run in isolation with a single writable workspace and filtered binary access.

---

## 5. Security notes

- **Unsafe**: Runs as the same user as the agent. Path validation limits access to `workspace_path`; use timeout to avoid hanging.
- **Safe**: Uses bwrap for namespace and filesystem isolation. The sandbox is not a full security boundary; use as a mitigation layer. Ensure `workspace_path` points to a dedicated workspace, not a sensitive directory.

---

## 6. Summary

| Item               | Description |
|--------------------|-------------|
| **RunCommandTool** | Runs shell commands; **unsafe** = OS subprocess (all platforms); **safe** = bwrap sandbox (Linux, requires bwrap). |
| **bwrap**          | Must be installed for safe mode. Install: [Bubblewrap - Installation](https://github.com/containers/bubblewrap#installation). |
| **Minimal defaults** | Safe mode uses a minimal bwrap setup: ro-bind /usr, workspace as /workspace, unshare-all, timeout. |
| **OverlayFS**      | When `include_paths`/`exclude_paths` are set, uses OverlayFS with whiteout files to exclude specific binaries from directories. |
