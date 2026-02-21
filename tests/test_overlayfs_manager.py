"""Tests for OverlayFSManager."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sgr_agent_core.agent_config import GlobalConfig
from sgr_agent_core.services.overlayfs_manager import OverlayFSManager


class TestOverlayFSManager:
    """Test suite for OverlayFSManager."""

    def test_initialize_from_config_reads_runcommand_config(self):
        """OverlayFSManager.initialize_from_config reads RunCommandTool config from GlobalConfig."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
        ):
            # Mock GlobalConfig
            mock_config_instance = MagicMock()
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {
                "mode": "safe",
                "include": ["ls", "cat"],
                "exclude": ["rm"],
            }
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_global_config.return_value = mock_config_instance

            # Mock binary collection
            with patch(
                "sgr_agent_core.services.overlayfs_manager._collect_allowed_binaries",
                return_value=({"/usr/bin/ls", "/usr/bin/cat"}, {}),
            ), patch(
                "sgr_agent_core.services.overlayfs_manager._resolve_command_path",
                return_value="/usr/bin/rm",
            ):
                OverlayFSManager.initialize_from_config()

            mock_init.assert_called_once()

    def test_initialize_from_config_skips_if_not_safe_mode(self):
        """OverlayFSManager.initialize_from_config skips if mode is not safe."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
        ):
            mock_config_instance = MagicMock()
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {"mode": "unsafe"}
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_global_config.return_value = mock_config_instance

            OverlayFSManager.initialize_from_config()

            mock_init.assert_not_called()

    def test_initialize_from_config_skips_if_no_include_exclude(self):
        """OverlayFSManager.initialize_from_config skips if include/exclude not set."""
        with (
            patch("sgr_agent_core.services.overlayfs_manager.GlobalConfig") as mock_global_config,
            patch("sgr_agent_core.services.overlayfs_manager.OverlayFSManager.initialize_overlayfs") as mock_init,
        ):
            mock_config_instance = MagicMock()
            mock_tool_def = MagicMock()
            mock_tool_def.tool_kwargs.return_value = {"mode": "safe"}
            mock_config_instance.tools = {"run_command_tool": mock_tool_def}
            mock_global_config.return_value = mock_config_instance

            OverlayFSManager.initialize_from_config()

            mock_init.assert_not_called()

    def test_cleanup_when_not_initialized_is_noop(self):
        """OverlayFSManager.cleanup when never initialized does nothing and does not raise."""
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
