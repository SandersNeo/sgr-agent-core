"""OverlayFS manager for RunCommandTool filesystem isolation.

Manages OverlayFS mounts created at server startup and unmounted at
shutdown.
"""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)


class OverlayFSManager:
    """Manages OverlayFS mounts for RunCommandTool.

    Creates overlay filesystems at startup based on tool configuration
    and unmounts them at shutdown.
    """

    _instance: ClassVar["OverlayFSManager | None"] = None
    _overlay_mounts: ClassVar[dict[str, str]] = {}  # original_dir -> merged_path
    _overlay_info: ClassVar[dict[str, str]] = {}  # merged_path -> "upper:work"
    _temp_base: ClassVar[Path | None] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def initialize_overlayfs(cls, allowed_binaries: set[str], excluded_binaries: set[str]) -> dict[str, str]:
        """Initialize OverlayFS mounts for given binaries.

        Args:
            allowed_binaries: Set of allowed binary paths
            excluded_binaries: Set of excluded binary paths

        Returns:
            Dict mapping original directory -> merged mount path
        """
        if cls._temp_base is None:
            cls._temp_base = Path(tempfile.mkdtemp(prefix="runcommand_overlay_"))
            logger.info("Created OverlayFS base directory: %s", cls._temp_base)

        # Group binaries by their parent directories
        dir_to_binaries: dict[str, set[str]] = {}
        for bin_path in allowed_binaries | excluded_binaries:
            bin_path_obj = Path(bin_path)
            parent_dir = str(bin_path_obj.parent)
            if parent_dir not in dir_to_binaries:
                dir_to_binaries[parent_dir] = set()
            dir_to_binaries[parent_dir].add(bin_path)

        for original_dir, binaries in dir_to_binaries.items():
            if original_dir in cls._overlay_mounts:
                # Already mounted, skip
                continue

            # Create temp directories for this overlay
            dir_name = original_dir.replace("/", "_").lstrip("_")
            lower_dir = Path(original_dir)
            upper_dir = cls._temp_base / f"upper_{dir_name}"
            work_dir = cls._temp_base / f"work_{dir_name}"
            merged_dir = cls._temp_base / f"merged_{dir_name}"

            # Create directories
            upper_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            merged_dir.mkdir(parents=True, exist_ok=True)

            # Create whiteout files for excluded binaries in this directory
            for bin_path in binaries:
                if bin_path in excluded_binaries:
                    bin_name = Path(bin_path).name
                    # Create whiteout file: .wh.<filename>
                    whiteout_path = upper_dir / f".wh.{bin_name}"
                    if not whiteout_path.exists():
                        # Create as character device 0/0 (whiteout format)
                        try:
                            os.mknod(str(whiteout_path), 0o000 | 0o200000, os.makedev(0, 0))
                        except (OSError, PermissionError):
                            # Fallback: create as regular file
                            whiteout_path.touch()

            # Mount overlayfs
            try:
                lower_str = str(lower_dir.resolve())
                upper_str = str(upper_dir.resolve())
                work_str = str(work_dir.resolve())
                merged_str = str(merged_dir.resolve())

                mount_cmd = [
                    "mount",
                    "-t",
                    "overlay",
                    "overlay",
                    "-o",
                    f"lowerdir={lower_str},upperdir={upper_str},workdir={work_str}",
                    merged_str,
                ]

                result = subprocess.run(mount_cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    logger.warning("Failed to mount overlayfs for %s: %s", original_dir, result.stderr)
                    continue

                cls._overlay_mounts[original_dir] = merged_str
                cls._overlay_info[merged_str] = f"{upper_str}:{work_str}"
                logger.info("Mounted OverlayFS: %s -> %s", original_dir, merged_str)

            except Exception:
                logger.exception("Error creating overlayfs for %s", original_dir)

        return cls._overlay_mounts.copy()

    @classmethod
    def get_overlay_mounts(cls) -> dict[str, str]:
        """Get current overlay mounts.

        Returns:
            Dict mapping original directory -> merged mount path
        """
        return cls._overlay_mounts.copy()

    @classmethod
    def cleanup(cls) -> None:
        """Unmount all overlay filesystems and clean up temporary
        directories."""
        for merged_path in list(cls._overlay_mounts.values()):
            try:
                subprocess.run(["umount", merged_path], capture_output=True, check=False)
                logger.info("Unmounted OverlayFS: %s", merged_path)
            except Exception:
                logger.warning("Failed to unmount OverlayFS: %s", merged_path)

        cls._overlay_mounts.clear()
        cls._overlay_info.clear()

        if cls._temp_base and cls._temp_base.exists():
            try:
                shutil.rmtree(cls._temp_base)
                logger.info("Cleaned up OverlayFS base directory: %s", cls._temp_base)
            except Exception:
                logger.warning("Failed to clean up OverlayFS base directory: %s", cls._temp_base)
            cls._temp_base = None
