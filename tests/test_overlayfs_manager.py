"""Tests for OverlayFSManager."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sgr_agent_core.services.overlayfs_manager import OverlayFSManager


class TestOverlayFSManager:
    """Test suite for OverlayFSManager."""

    def test_initialize_from_config_reads_runcommand_config(self):
        """OverlayFSManager.initialize_from_config reads RunCommandTool config
        from GlobalConfig."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
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
                OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()

    def test_initialize_from_config_exits_when_tool_used_but_workspace_path_not_set(
        self,
    ):
        """When RunCommandTool is used (global or agent) and no candidate has
        workspace_path set, initialize_from_config logs error and exits."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
            patch("sgr_agent_core.services.overlayfs_manager.sys.exit") as mock_exit,
        ):
            mock_exit.side_effect = SystemExit(1)
            mock_config_instance = MagicMock()
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {"mode": "safe"}
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_config_instance.agents = {}
            mock_global_config.return_value = mock_config_instance

            with pytest.raises(SystemExit, match="1"):
                OverlayFSManager.initialize_from_config()

            mock_exit.assert_called_once_with(1)
            mock_init.assert_not_called()

    def test_initialize_from_config_does_not_exit_when_tool_not_used(self):
        """When RunCommandTool is not used anywhere, no exit and no init."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
            patch("sgr_agent_core.services.overlayfs_manager.sys.exit") as mock_exit,
        ):
            mock_config_instance = MagicMock()
            mock_config_instance.tools = {}
            mock_config_instance.agents = {}
            mock_global_config.return_value = mock_config_instance

            OverlayFSManager.initialize_from_config()

            mock_exit.assert_not_called()
            mock_init.assert_not_called()

    def test_initialize_from_config_does_not_exit_when_workspace_path_set(self):
        """When RunCommandTool is used and workspace_path is set, no exit."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
            patch("sgr_agent_core.services.overlayfs_manager.sys.exit") as mock_exit,
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

            OverlayFSManager.initialize_from_config()

            mock_exit.assert_not_called()
            mock_init.assert_called_once()

    def test_initialize_from_config_skips_when_all_unsafe(self, caplog):
        """OverlayFSManager.initialize_from_config skips when global and all
        agents use unsafe mode (no safe+include/exclude anywhere)."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
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
                OverlayFSManager.initialize_from_config()

            mock_init.assert_not_called()
            assert any("configured only with unsafe mode" in message for message in caplog.messages)

    def test_initialize_from_config_runs_when_global_unsafe_but_agent_safe(
        self,
    ):
        """OverlayFSManager.initialize_from_config runs when global is unsafe
        but at least one agent has safe+include (init if safe anywhere)."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
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

            OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()

    def test_initialize_from_config_runs_when_safe_without_paths(self):
        """OverlayFSManager.initialize_from_config runs when mode is safe even
        if include_paths/exclude_paths are not set (init if safe anywhere)."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
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

            OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()
            mock_init.assert_called_with(set(), set())

    def test_initialize_from_config_runs_when_run_command_tool_only_in_agent(
        self,
    ):
        """OverlayFSManager.initialize_from_config runs when RunCommandTool is
        only in an agent's tools (not in global) with safe+include."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
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

            OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()

    def test_initialize_from_config_skips_when_run_command_tool_nowhere(self):
        """OverlayFSManager.initialize_from_config skips when RunCommandTool is
        neither in global tools nor in any agent's tools."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
            patch(
                "sgr_agent_core.agent_factory.AgentFactory._resolve_tools_with_configs",
                return_value=([], {}),
            ),
        ):
            mock_config_instance = MagicMock()
            mock_config_instance.tools = {}
            mock_config_instance.agents = {"my_agent": MagicMock(tools=["web_search_tool"])}
            mock_global_config.return_value = mock_config_instance

            OverlayFSManager.initialize_from_config()

            mock_init.assert_not_called()

    def test_cleanup_when_not_initialized_is_noop(self):
        """OverlayFSManager.cleanup when never initialized does nothing and
        does not raise."""
        OverlayFSManager._overlay_mounts = {}
        OverlayFSManager._overlay_info = {}
        OverlayFSManager._temp_base = None

        OverlayFSManager.cleanup()

        assert len(OverlayFSManager._overlay_mounts) == 0
        assert len(OverlayFSManager._overlay_info) == 0
        assert OverlayFSManager._temp_base is None

    def test_cleanup_unmounts_all_overlays(self):
        """OverlayFSManager.cleanup unmounts all overlay filesystems."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.subprocess.run") as mock_subprocess,
            patch("sgr_agent_core.services.overlayfs_manager.shutil.rmtree") as mock_rmtree,
            patch("sgr_agent_core.services.overlayfs_manager.Path.exists", return_value=True),
        ):
            # Set up some mounts
            OverlayFSManager._overlay_mounts = {"/usr/bin": "/tmp/merged_usr_bin"}
            OverlayFSManager._overlay_info = {"/tmp/merged_usr_bin": "/tmp/upper:/tmp/work"}
            OverlayFSManager._temp_base = Path("/tmp/test_overlay")

            OverlayFSManager.cleanup()

            # Check that umount was called
            mock_subprocess.assert_called()
            # Check that rmtree was called for temp_base
            mock_rmtree.assert_called()
            # Check that mounts were cleared
            assert len(OverlayFSManager._overlay_mounts) == 0
            assert OverlayFSManager._temp_base is None
