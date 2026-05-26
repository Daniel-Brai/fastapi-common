import json
from pathlib import Path

from lib.assets.types import AssetMode


class AssetManager:
    """
    Asset manager that reads a manifest (for renamed/hashed files) and provides
    versioned URLs for static assets.

    - rename mode: uses hashed filenames (e.g., main.abc123.css)
    - query mode: adds ?v=hash (e.g., main.css?v=abc123)

    For files not in manifest (e.g., images), it falls back to query-string
    versioning based on file modification time.
    """

    def __init__(
        self,
        manifest_path: Path | None = None,
        static_url: str = "/static",
        mode: AssetMode = "rename",
        static_dir: Path | None = None,
    ) -> None:
        self.manifest_path = manifest_path
        self.static_url = static_url.rstrip("/")
        self.mode = mode
        self.static_dir = static_dir

        self._manifest: dict[str, str] = {}
        self._file_versions: dict[str, str] = {}

        if manifest_path and manifest_path.exists():
            self._load_manifest(manifest_path)

        if static_dir and static_dir.exists():
            self._scan_static_files()

    def _load_manifest(self, manifest_path: Path) -> None:
        """
        Load manifest JSON mapping original filename → versioned name.
        """
        with open(manifest_path) as f:
            data = json.load(f)

        for original, hashed in data.items():
            if self.mode == "query":
                # Extract hash from hashed filename (e.g., "abc123" from "main-abc123.css")
                # Assumes hash is the last part before extension.
                # If the filename doesn't contain a hash, fallback to entire name.
                import re

                match = re.search(r"-([a-f0-9]{8,})\.", hashed)
                if match:
                    version = match.group(1)
                else:
                    # If no hash pattern found, use full hashed filename as version
                    version = hashed
                self._manifest[original] = version
            else:
                self._manifest[original] = hashed

    def _scan_static_files(self) -> None:
        """
        Pre compute versions for all files in static_dir
        """
        if not self.static_dir:
            return

        for file_path in self.static_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self.static_dir).as_posix()
                self._file_versions[rel_path] = self._compute_version(file_path)

    def _compute_version(self, file_path: Path) -> str:
        """
        Return a version identifier for a file (e.g., its modification timestamp).
        """
        return str(int(file_path.stat().st_mtime))

    def url_for(self, filename: str) -> str:
        """
        Return the asset URL with cache busting applied.

        For files in the manifest, use rename or query mode.
        For others, fallback to query-string with mtime.
        """

        if filename in self._manifest:
            if self.mode == "rename":
                asset_name = self._manifest[filename]
                return f"{self.static_url}/{asset_name}"
            else:
                version = self._manifest[filename]
                return f"{self.static_url}/{filename}?v={version}"

        if self.static_dir and filename in self._file_versions:
            version = self._file_versions[filename]
            return f"{self.static_url}/{filename}?v={version}"

        return f"{self.static_url}/{filename}"

    def reload_manifest(self, manifest_path: Path) -> None:
        """
        Reload the manifest (useful during development)
        """
        self._manifest.clear()
        self._load_manifest(manifest_path)
