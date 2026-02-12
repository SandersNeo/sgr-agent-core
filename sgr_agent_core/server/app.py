"""FastAPI application instance creation and configuration."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sgr_agent_core import AgentFactory, AgentRegistry, ToolRegistry, __version__
from sgr_agent_core.agent_config import GlobalConfig
from sgr_agent_core.server.endpoints import router
from sgr_agent_core.services import StreamingGeneratorRegistry
from sgr_agent_core.services.overlayfs_manager import OverlayFSManager
from sgr_agent_core.tools.run_command_tool import (
    RunCommandToolConfig,
    _collect_allowed_binaries,
    _resolve_command_path,
)

logger = logging.getLogger(__name__)


def _initialize_runcommand_overlayfs() -> None:
    """Initialize OverlayFS for RunCommandTool if configured."""
    try:
        config = GlobalConfig()
        runcommand_config = config.tools.get("run_command_tool") or config.tools.get("runcommandtool")
        if not runcommand_config:
            return

        # Get tool config
        tool_config_dict = runcommand_config.tool_kwargs() if hasattr(runcommand_config, "tool_kwargs") else {}
        tool_config = RunCommandToolConfig(**tool_config_dict)

        # Only initialize if include/exclude are set and mode is safe
        if tool_config.mode != "safe" or (not tool_config.include and not tool_config.exclude):
            return

        # Collect binaries
        allowed_binaries, _ = _collect_allowed_binaries(tool_config.include, tool_config.exclude)
        excluded_binaries = set()
        if tool_config.exclude:
            for excl_item in tool_config.exclude:
                excl_path = _resolve_command_path(excl_item) if "/" not in excl_item else None
                if not excl_path:
                    try:
                        from pathlib import Path

                        p = Path(excl_item).resolve()
                        if p.is_file() or p.exists():
                            excl_path = str(p)
                    except Exception:
                        continue
                if excl_path:
                    try:
                        from pathlib import Path

                        if Path(excl_path).exists() and Path(excl_path).is_file():
                            excluded_binaries.add(excl_path)
                    except Exception:
                        pass

        if allowed_binaries or excluded_binaries:
            mounts = OverlayFSManager.initialize_overlayfs(allowed_binaries, excluded_binaries)
            logger.info("Initialized OverlayFS for RunCommandTool: %d mounts", len(mounts))
    except Exception:
        logger.exception("Failed to initialize OverlayFS for RunCommandTool")


@asynccontextmanager
async def lifespan(_: FastAPI):
    for tool in ToolRegistry.list_items():
        logger.info(f"Tool registered: {tool.__name__}")
    for agent in AgentRegistry.list_items():
        logger.info(f"Agent registered: {agent.__name__}")
    for defn in AgentFactory.get_definitions_list():
        logger.info(f"Agent definition loaded: {defn}")
    for gen in StreamingGeneratorRegistry.list_items():
        logger.info(f"Streaming generator loaded: {gen.__name__}")

    # Initialize OverlayFS for RunCommandTool if configured
    _initialize_runcommand_overlayfs()

    yield

    # Cleanup OverlayFS on shutdown
    OverlayFSManager.cleanup()


app = FastAPI(title="SGR Agent Core API", version=__version__, lifespan=lifespan)
# Don't use this CORS setting in production!
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
