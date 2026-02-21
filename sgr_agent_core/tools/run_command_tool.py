"""RunCommandTool: execute shell commands in unsafe (OS) or safe (bwrap) mode."""

from __future__ import annotations

import asyncio
import logging
import shlex
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, Field

from sgr_agent_core.base_tool import BaseTool

if TYPE_CHECKING:
    from sgr_agent_core.agent_definition import AgentConfig
    from sgr_agent_core.models import AgentContext

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 60

# Installation instructions when bwrap is not found (safe mode, Linux).
BWRAP_INSTALL_URL = "https://github.com/containers/bubblewrap#installation"


class RunCommandToolConfig(BaseModel):
    """Config model for RunCommandTool (built from kwargs only, no global
    section)."""

    root_path: str | None = None
    mode: str = "safe"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    include_paths: list[str] | None = None  # Allowed commands/paths (priority over exclude_paths)
    exclude_paths: list[str] | None = None  # Excluded commands/paths (ignored if also in include_paths)


def _resolve_command_path(command_name: str) -> str | None:
    """Resolve command name to full path (which/realpath)."""
    if not command_name:
        return None
    if "/" in command_name:
        try:
            return str(Path(command_name).resolve())
        except Exception:
            return None
    resolved = shutil.which(command_name)
    if resolved:
        try:
            return str(Path(resolved).resolve())
        except Exception:
            return resolved
    return None


def _check_allowed(
    command: str,
    include_paths: list[str] | None,
    exclude_paths: list[str] | None,
    root_path: Path | None,
) -> str | None:
    """Check if command and its paths are allowed. include_paths has priority
    over exclude_paths (same path in both is allowed).

    Returns error message if not allowed, None if allowed.
    """
    if not include_paths and not exclude_paths:
        return None

    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()

    if not parts:
        return None

    cmd_name = parts[0]
    cmd_path = _resolve_command_path(cmd_name)
    cmd_to_check = cmd_path if cmd_path else cmd_name

    def _matches(item: str, resolved: str | None, path: str | None) -> bool:
        return (
            cmd_name == item
            or (cmd_path and resolved and cmd_path == resolved)
            or (cmd_path and path and cmd_path == path)
            or (cmd_to_check == path)
        )

    # include_paths has priority: if command matches include_paths, allow
    if include_paths:
        for incl_item in include_paths:
            incl_resolved = _resolve_command_path(incl_item) if "/" not in incl_item else None
            incl_path = None
            try:
                incl_path = str(Path(incl_item).resolve()) if incl_item.startswith("/") else None
            except Exception:
                pass
            if _matches(incl_item, incl_resolved, incl_path):
                return None

    # exclude_paths: reject only if not in include_paths (already returned None above if included)
    if exclude_paths:
        for excl_item in exclude_paths:
            excl_resolved = _resolve_command_path(excl_item) if "/" not in excl_item else None
            excl_path = None
            try:
                excl_path = str(Path(excl_item).resolve()) if excl_item.startswith("/") else None
            except Exception:
                pass
            if _matches(excl_item, excl_resolved, excl_path):
                return f"Command '{cmd_name}' is excluded: {excl_item}"

    # include_paths set but no match
    if include_paths:
        return f"Command '{cmd_name}' is not in include_paths. Allowed: {include_paths}"

    # Check paths in arguments (if root_path is set)
    if root_path:
        for part in parts[1:]:
            if not part or part.startswith("-"):
                continue
            if "/" in part or part in (".", "..") or part.startswith("./") or part.startswith(".."):
                try:
                    resolved = Path(part).resolve() if part.startswith("/") else (root_path / part).resolve()
                    if resolved != root_path:
                        resolved.relative_to(root_path)
                    path_str = str(resolved)
                    if exclude_paths:
                        for excl_item in exclude_paths:
                            excl_resolved = _resolve_command_path(excl_item) if "/" not in excl_item else None
                            excl_path = None
                            try:
                                excl_path = str(Path(excl_item).resolve()) if excl_item.startswith("/") else None
                            except Exception:
                                pass
                            if (
                                path_str == excl_item
                                or path_str == excl_resolved
                                or path_str == excl_path
                                or (excl_path and path_str.startswith(excl_path + "/"))
                            ):
                                return f"Path '{part}' is excluded: {excl_item}"
                except ValueError:
                    return f"Path escape not allowed: '{part}' is outside root {root_path}"
                except Exception:
                    pass

    return None


def _validate_command_paths(command: str, root_path: Path) -> str | None:
    """If any path-like token in command escapes root_path, return error
    message; else None."""
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    for part in parts:
        if not part or part.startswith("-"):
            continue
        if "/" in part or part in (".", "..") or part.startswith("./") or part.startswith(".."):
            try:
                resolved = Path(part).resolve() if part.startswith("/") else (root_path / part).resolve()
                if resolved != root_path:
                    resolved.relative_to(root_path)
            except ValueError:
                return f"Path escape not allowed: '{part}' is outside root {root_path}"
            except Exception:
                pass
    return None


def _collect_allowed_binaries(
    include_paths: list[str] | None, exclude_paths: list[str] | None
) -> tuple[set[str], dict[str, str]]:
    """Collect allowed binary paths. include_paths has priority over
    exclude_paths (path in both is kept allowed).

    Returns:
        Tuple of (allowed_paths_set, dir_mapping). dir_mapping is unused (legacy).
    """
    if not include_paths:
        return set(), {}

    allowed_binaries: set[str] = set()
    excluded_binaries: set[str] = set()

    for incl_item in include_paths:
        incl_path = None
        if "/" not in incl_item:
            incl_path = _resolve_command_path(incl_item)
        else:
            try:
                p = Path(incl_item).resolve()
                if p.is_dir():
                    continue
                if p.is_file() or p.exists():
                    incl_path = str(p)
            except Exception:
                continue
        if incl_path and Path(incl_path).exists() and Path(incl_path).is_file():
            allowed_binaries.add(incl_path)

    if exclude_paths:
        for excl_item in exclude_paths:
            excl_path = None
            if "/" not in excl_item:
                excl_path = _resolve_command_path(excl_item)
            else:
                try:
                    p = Path(excl_item).resolve()
                    if p.is_file() or p.exists():
                        excl_path = str(p)
                except Exception:
                    continue
            if excl_path and Path(excl_path).exists() and Path(excl_path).is_file():
                excluded_binaries.add(excl_path)

    # include_paths has priority: remove only excluded that are not in allowed
    allowed_binaries -= excluded_binaries - allowed_binaries

    return allowed_binaries, {}


def _bwrap_argv(
    workspace: Path,
    allowed_dirs: set[str] | None = None,
    overlay_mounts: dict[str, str] | None = None,
) -> list[str]:
    """Build bwrap args: mount allowed dirs or overlay mounts (or default /usr), proc, dev, bind workspace, unshare.

    If overlay_mounts is provided, mounts overlay filesystems (merged layers) at their original locations.
    If allowed_dirs is provided and not empty, mounts only those directories (plus /lib, /usr/lib
    for dependencies, /proc, /dev). Otherwise uses default: ro-bind /usr, symlinks.
    """
    work_str = str(workspace.resolve())
    args = []

    if overlay_mounts:
        # Mount overlay filesystems (merged layers) at their original locations
        for original_dir, merged_path in overlay_mounts.items():
            try:
                if Path(merged_path).exists():
                    args.extend(["--bind", merged_path, original_dir])
            except Exception:
                pass

        # Always mount essential system dirs for shared libraries
        essential_dirs = {"/lib", "/usr/lib", "/usr/lib64", "/lib64"}
        for dir_path in sorted(essential_dirs):
            try:
                if Path(dir_path).exists():
                    args.extend(["--ro-bind", dir_path, dir_path])
            except Exception:
                pass

        # Create symlinks for compatibility
        if any("/usr/bin" in d or d == "/usr/bin" for d in overlay_mounts.keys()):
            args.extend(["--symlink", "usr/bin", "/bin"])
        args.extend(["--symlink", "usr/lib", "/lib"])
        args.extend(["--symlink", "usr/lib64", "/lib64"])
    elif allowed_dirs:
        # Mount only allowed directories + essential system dirs for dependencies
        # Mount /lib and /usr/lib for shared libraries
        essential_dirs = {"/lib", "/usr/lib", "/usr/lib64", "/lib64"}
        all_dirs = allowed_dirs | essential_dirs

        # Sort for consistent ordering
        for dir_path in sorted(all_dirs):
            try:
                if Path(dir_path).exists():
                    args.extend(["--ro-bind", dir_path, dir_path])
            except Exception:
                pass

        # Create symlinks for compatibility if /usr/bin is mounted
        if any("/usr/bin" in d or d == "/usr/bin" for d in allowed_dirs):
            args.extend(["--symlink", "usr/bin", "/bin"])
        if any("/usr/lib" in d or d == "/usr/lib" for d in all_dirs):
            args.extend(["--symlink", "usr/lib", "/lib"])
        if any("/usr/lib64" in d or d == "/usr/lib64" for d in all_dirs):
            args.extend(["--symlink", "usr/lib64", "/lib64"])
    else:
        # Default: mount /usr and create symlinks
        args.extend(
            [
                "--ro-bind",
                "/usr",
                "/usr",
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/lib",
                "/lib",
                "--symlink",
                "usr/lib64",
                "/lib64",
            ]
        )

    # Always mount proc, dev, workspace
    args.extend(
        [
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--bind",
            work_str,
            "/workspace",
            "--chdir",
            "/workspace",
            "--unshare-all",
            "--die-with-parent",
            "--",
            "/bin/sh",
            "-c",
        ]
    )

    return args


class RunCommandTool(BaseTool):
    """Execute a shell command in unsafe (OS subprocess) or safe (bwrap) mode.

    Unsafe: runs via OS (asyncio subprocess), optional root_path restricts to a directory.
    Safe: runs via Bubblewrap (bwrap) with minimal defaults; Linux only, requires bwrap
    to be installed. If bwrap is not found, returns an error with installation link.
    """

    tool_name: ClassVar[str] = "runcommandtool"
    description: ClassVar[str] = (
        "Execute a shell command. Use for running scripts, listing files, or system checks. "
        "Unsafe mode runs via OS; safe mode uses Bubblewrap (bwrap) sandbox on Linux."
    )

    reasoning: str = Field(description="Why this command is needed")
    command: str = Field(description="Full command line to execute (e.g. ls -la, python script.py)")

    async def __call__(self, context: AgentContext, config: AgentConfig, **kwargs: Any) -> str:
        """Run the command in unsafe or safe mode according to config."""
        allowed = {"root_path", "mode", "timeout_seconds", "include_paths", "exclude_paths"}
        cfg_dict = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        cfg = RunCommandToolConfig(**cfg_dict)
        root_path_obj = Path(cfg.root_path).expanduser().resolve() if cfg.root_path else None
        err = _check_allowed(self.command, cfg.include_paths, cfg.exclude_paths, root_path_obj)
        if err:
            return f"Error: {err}"
        if cfg.mode == "safe":
            return await self._run_safe(cfg)
        return await self._run_unsafe(cfg)

    async def _run_safe(self, cfg: RunCommandToolConfig) -> str:
        """Execute via bwrap; require bwrap in PATH and return error with
        install link if missing."""
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            return (
                "Error: Safe mode requires Bubblewrap (bwrap) to be installed. "
                f"Install: {BWRAP_INSTALL_URL} "
                "(e.g. Debian/Ubuntu: apt install bubblewrap). Safe mode is Linux only."
            )
        workspace = Path(cfg.root_path).expanduser().resolve() if cfg.root_path else Path("/tmp")
        if not workspace.exists() or not workspace.is_dir():
            return f"Error: root_path does not exist or is not a directory: {workspace}"

        # If include_paths/exclude_paths are set, use pre-initialized OverlayFS from OverlayFSManager
        overlay_mounts = None
        if cfg.include_paths or cfg.exclude_paths:
            from sgr_agent_core.services.overlayfs_manager import OverlayFSManager

            overlay_mounts = OverlayFSManager.get_overlay_mounts()
            if not overlay_mounts:
                logger.warning(
                    "OverlayFS mounts not initialized. "
                    "Start server with RunCommandTool config including include_paths/exclude_paths."
                )

        argv = [bwrap_path] + _bwrap_argv(workspace, allowed_dirs=None, overlay_mounts=overlay_mounts) + [self.command]
        logger.info("RunCommandTool executing (safe/bwrap): %s", self.command[:200])
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )
        except Exception as e:
            logger.exception("RunCommandTool bwrap exec failed")
            return f"Error: {e!s}"
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=cfg.timeout_seconds)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return f"Error: Command timed out after {cfg.timeout_seconds} seconds."
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        return_code = process.returncode or 0

        # OverlayFS mounts are managed by OverlayFSManager and cleaned up at server shutdown
        # No cleanup needed here

        return self._format_result(out, err, return_code)

    async def _run_unsafe(self, cfg: RunCommandToolConfig) -> str:
        """Execute via OS subprocess with optional root_path as cwd and path
        validation."""
        cwd = None
        if cfg.root_path:
            root = Path(cfg.root_path).expanduser().resolve()
            if not root.exists():
                return f"Error: root_path does not exist: {cfg.root_path}"
            if not root.is_dir():
                return f"Error: root_path is not a directory: {cfg.root_path}"
            err = _validate_command_paths(self.command, root)
            if err:
                return f"Error: {err}"
            cwd = str(root)

        logger.info("RunCommandTool executing (unsafe): %s", self.command[:200])
        try:
            process = await asyncio.create_subprocess_shell(
                self.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=cfg.timeout_seconds)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return f"Error: Command timed out after {cfg.timeout_seconds} seconds."
            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            return self._format_result(out, err, process.returncode or 0)
        except Exception as e:
            logger.exception("RunCommandTool subprocess failed")
            return f"Error: {e!s}"

    @staticmethod
    def _format_result(stdout: str, stderr: str, return_code: int) -> str:
        """Format stdout, stderr and return_code into a single string."""
        lines = []
        if stdout:
            lines.append(f"stdout:\n{stdout.rstrip()}")
        if stderr:
            lines.append(f"stderr:\n{stderr.rstrip()}")
        lines.append(f"return_code: {return_code}")
        return "\n\n".join(lines)
