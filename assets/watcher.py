from pathlib import Path

from watchfiles import awatch

from lib.assets.manager import AssetManager
from lib.logger import get_logger

logger = get_logger("lib.assets.watcher")


async def watch_manifest(manager: AssetManager, manifest_path: Path):
    """
    Watches the manifest file for changes and reloads it in the asset manager when it changes.
    """

    async for _ in awatch(manifest_path.parent):
        if manifest_path.exists():
            manager.reload_manifest(manifest_path)
            logger.info("Manifest reloaded")
