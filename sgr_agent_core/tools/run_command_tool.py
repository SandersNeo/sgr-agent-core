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
    mode: str = "unsafe"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


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


def _bwrap_argv(workspace: Path) -> list[str]:
    """Build minimal bwrap args: ro-bind /usr, symlinks, proc, dev, bind workspace, unshare."""
    work_str = str(workspace.resolve())
    return [
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
        allowed = {"root_path", "mode", "timeout_seconds"}
        cfg_dict = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        cfg = RunCommandToolConfig(**cfg_dict)
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
        argv = [bwrap_path] + _bwrap_argv(workspace) + [self.command]
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
        return self._format_result(out, err, process.returncode or 0)

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
