"""Tests for OverlayFSManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sgr_agent_core.services.overlayfs_manager import OverlayFSManager


class TestOverlayFSManager:
    """Test suite for OverlayFSManager."""

    @pytest.mark.asyncio
    async def test_initialize_from_config_reads_runcommand_config(self):
        """OverlayFSManager.initialize_from_config reads RunCommandTool config
        from GlobalConfig."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch(
                "sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_init,
        ):
            # Mock GlobalConfig
            mock_config_instance = MagicMock()
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {
                "mode": "safe",
                "workspace_path": "/tmp/workspace",
                "include_paths": ["ls", "cat"],
                "exclude_paths": ["rm"],
            }
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_config_instance.agents = {}
            mock_global_config.return_value = mock_config_instance

            # Mock binary collection
            with (
                patch(
                    "sgr_agent_core.services.overlayfs_manager._collect_allowed_binaries",
                    return_value=({"/usr/bin/ls", "/usr/bin/cat"}, {}),
                ),
                patch(
                    "sgr_agent_core.services.overlayfs_manager._resolve_command_path",
                    return_value="/usr/bin/rm",
                ),
            ):
                await OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_from_config_creates_default_workspace_when_not_set(self, tmp_path, caplog):
        """When RunCommandTool is used with safe mode and workspace_path is not
        set, initialize_from_config creates ./workspace near config.yaml and
        uses it instead of exiting."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch(
                "sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_init,
            patch(
                "sgr_agent_core.services.overlayfs_manager._collect_allowed_binaries",
                return_value=(set(), {}),
            ),
        ):
            mock_config_instance = MagicMock()
            mock_config_instance.config_dir = tmp_path
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {"mode": "safe"}
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_config_instance.agents = {}
            mock_global_config.return_value = mock_config_instance

            workspace_dir = tmp_path / "workspace"
            with caplog.at_level("WARNING"):
                await OverlayFSManager.initialize_from_config()

            assert workspace_dir.exists() and workspace_dir.is_dir()
            mock_init.assert_called_once()
            assert any(
                "workspace_path is not set; using default workspace directory" in message for message in caplog.messages
            )

    @pytest.mark.asyncio
    async def test_initialize_from_config_does_not_exit_when_tool_not_used(self):
        """When RunCommandTool is not used anywhere, no exit and no init."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch(
                "sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_init,
        ):
            mock_config_instance = MagicMock()
            mock_config_instance.tools = {}
            mock_config_instance.agents = {}
            mock_global_config.return_value = mock_config_instance

            await OverlayFSManager.initialize_from_config()

            mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_from_config_does_not_exit_when_workspace_path_set(self):
        """When RunCommandTool is used and workspace_path is set, no exit."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch(
                "sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_init,
            patch(
                "sgr_agent_core.services.overlayfs_manager._collect_allowed_binaries",
                return_value=(set(), {}),
            ),
        ):
            mock_config_instance = MagicMock()
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {
                "mode": "safe",
                "workspace_path": "/tmp/workspace",
            }
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_config_instance.agents = {}
            mock_global_config.return_value = mock_config_instance

            await OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_from_config_skips_when_all_unsafe(self, caplog):
        """OverlayFSManager.initialize_from_config skips when global and all
        agents use unsafe mode (no safe+include/exclude anywhere)."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch(
                "sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_init,
            patch(
                "sgr_agent_core.agent_factory.AgentFactory._resolve_tools_with_configs",
                return_value=([], {"runcommandtool": {"mode": "unsafe"}}),
            ),
        ):
            mock_config_instance = MagicMock()
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {"mode": "unsafe"}
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_config_instance.agents = {"ag": MagicMock(tools=["run_command_tool"])}
            mock_global_config.return_value = mock_config_instance

            with caplog.at_level("WARNING"):
                await OverlayFSManager.initialize_from_config()

            mock_init.assert_not_called()
            assert any("configured only with unsafe mode" in message for message in caplog.messages)

    @pytest.mark.asyncio
    async def test_initialize_from_config_runs_when_global_unsafe_but_agent_safe(
        self,
    ):
        """OverlayFSManager.initialize_from_config runs when global is unsafe
        but at least one agent has safe+include (init if safe anywhere)."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch(
                "sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_init,
            patch(
                "sgr_agent_core.agent_factory.AgentFactory._resolve_tools_with_configs",
                return_value=(
                    [],
                    {
                        "runcommandtool": {
                            "mode": "safe",
                            "workspace_path": "/tmp/workspace",
                            "include_paths": ["ls", "cat"],
                            "exclude_paths": ["rm"],
                        }
                    },
                ),
            ),
            patch(
                "sgr_agent_core.services.overlayfs_manager._collect_allowed_binaries",
                return_value=({"/usr/bin/ls", "/usr/bin/cat"}, {}),
            ),
            patch(
                "sgr_agent_core.services.overlayfs_manager._resolve_command_path",
                return_value="/usr/bin/rm",
            ),
        ):
            mock_config_instance = MagicMock()
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {"mode": "unsafe"}
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_config_instance.agents = {"ag": MagicMock(tools=["run_command_tool"])}
            mock_global_config.return_value = mock_config_instance

            await OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_from_config_runs_when_safe_without_paths(self):
        """OverlayFSManager.initialize_from_config runs when mode is safe even
        if include_paths/exclude_paths are not set (init if safe anywhere)."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch(
                "sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_init,
        ):
            mock_config_instance = MagicMock()
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {
                "mode": "safe",
                "workspace_path": "/tmp/workspace",
            }
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_config_instance.agents = {}
            mock_global_config.return_value = mock_config_instance

            await OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()
            mock_init.assert_called_with(set(), set())

    @pytest.mark.asyncio
    async def test_initialize_from_config_runs_when_run_command_tool_only_in_agent(
        self,
    ):
        """OverlayFSManager.initialize_from_config runs when RunCommandTool is
        only in an agent's tools (not in global) with safe+include."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch(
                "sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_init,
            patch(
                "sgr_agent_core.agent_factory.AgentFactory._resolve_tools_with_configs",
                return_value=(
                    [],
                    {
                        "runcommandtool": {
                            "mode": "safe",
                            "workspace_path": "/tmp/workspace",
                            "include_paths": ["ls", "cat"],
                            "exclude_paths": ["rm"],
                        }
                    },
                ),
            ),
            patch(
                "sgr_agent_core.services.overlayfs_manager._collect_allowed_binaries",
                return_value=({"/usr/bin/ls", "/usr/bin/cat"}, {}),
            ),
            patch(
                "sgr_agent_core.services.overlayfs_manager._resolve_command_path",
                return_value="/usr/bin/rm",
            ),
        ):
            mock_config_instance = MagicMock()
            mock_config_instance.tools = {}
            mock_config_instance.agents = {
                "my_agent": MagicMock(
                    tools=[
                        {
                            "name": "run_command_tool",
                            "mode": "safe",
                            "workspace_path": "/tmp/workspace",
                            "include_paths": ["ls", "cat"],
                            "exclude_paths": ["rm"],
                        }
                    ]
                )
            }
            mock_global_config.return_value = mock_config_instance

            await OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_from_config_skips_when_run_command_tool_nowhere(self):
        """OverlayFSManager.initialize_from_config skips when RunCommandTool is
        neither in global tools nor in any agent's tools."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch(
                "sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_init,
            patch(
                "sgr_agent_core.agent_factory.AgentFactory._resolve_tools_with_configs",
                return_value=([], {}),
            ),
        ):
            mock_config_instance = MagicMock()
            mock_config_instance.tools = {}
            mock_config_instance.agents = {"my_agent": MagicMock(tools=["web_search_tool"])}
            mock_global_config.return_value = mock_config_instance

            await OverlayFSManager.initialize_from_config()

            mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_when_not_initialized_is_noop(self):
        """OverlayFSManager.cleanup when never initialized does nothing and
        does not raise."""
        OverlayFSManager._overlay_mounts = {}
        OverlayFSManager._overlay_info = {}
        OverlayFSManager._temp_base = None

        await OverlayFSManager.cleanup()

        assert len(OverlayFSManager._overlay_mounts) == 0
        assert len(OverlayFSManager._overlay_info) == 0
        assert OverlayFSManager._temp_base is None

    @pytest.mark.asyncio
    async def test_cleanup_unmounts_all_overlays(self, tmp_path):
        """OverlayFSManager.cleanup unmounts all overlay filesystems."""

        async def _fake_communicate() -> tuple[None, None]:
            return (None, None)

        fake_process = AsyncMock()
        fake_process.communicate = _fake_communicate
        fake_process.returncode = 0

        async def _fake_to_thread(fn: object, *args: object, **kwargs: object) -> object:
            return fn(*args, **kwargs)  # type: ignore[misc]

        temp_base = tmp_path / "overlay_base"
        temp_base.mkdir()

        with (
            patch(
                "sgr_agent_core.services.overlayfs_manager.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=fake_process,
            ) as mock_exec,
            patch(
                "sgr_agent_core.services.overlayfs_manager.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ),
        ):
            OverlayFSManager._overlay_mounts = {"/usr/bin": "/tmp/merged_usr_bin"}
            OverlayFSManager._overlay_info = {"/tmp/merged_usr_bin": "/tmp/upper:/tmp/work"}
            OverlayFSManager._temp_base = temp_base

            await OverlayFSManager.cleanup()

            mock_exec.assert_called()
            assert len(OverlayFSManager._overlay_mounts) == 0
            assert OverlayFSManager._temp_base is None
