from pathlib import Path

from lib.assets.manager import AssetManager, AssetMode
from lib.templates.types import TemplateEngine


def configure_asset_manager(
    engine: TemplateEngine,
    manifest_path: Path | None = None,
    static_url: str = "/static",
    mode: AssetMode = "rename",
    static_dir: Path | None = None,
) -> AssetManager:
    """
    Configures the asset manager for the template engine.
    """

    manager = AssetManager(manifest_path, static_url, mode, static_dir)
    engine.env.globals["asset"] = manager.url_for

    return manager
