import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

from lib.logger import get_logger

logger = get_logger("lib.assets.builder")


class AssetBuilder:
    """
    Builder for static assets using esbuild.

    It processes entry points, generates hashed filenames, creates a manifest mapping original names to hashed names, and copies specified files verbatim (e.g., PWA files).

    The build process is configurable with options for minification, sourcemaps, and custom naming patterns.

    Parameters
    ----------
        static_src : str | Path
            Source directory containing unprocessed assets.
        static_dist : str | Path
            Destination directory for built assets.
        entry_points : list[str | Path]
            Files to be processed by esbuild (CSS, JS, etc.).
        pwa_files : list[str | Path], optional
            Files that must NOT be hashed (e.g., service-worker.js, manifest.json).
            They will be copied as-is to static_dist.
        copy_files : list[str | Path], optional
            Additional files to copy verbatim (e.g., favicon.ico).
        minify : bool
            Whether to minify output (default True).
        sourcemap : bool
            Whether to generate sourcemaps (default True).
        asset_names : str
            Pattern for asset names (default "[name]-[hash]").
        entry_names : str
            Pattern for entry point names (default "[name]-[hash]").
        outbase : str | Path, optional
            Base directory for output structure (defaults to static_src).
        extra_esbuild_args : list[str], optional
            Extra arguments to pass to esbuild.

    Usage::

        builder = AssetBuilder(
            static_src="assets/src",
            static_dist="assets/dist",
            entry_points=["assets/src/app.js", "assets/src/styles.css"],
            pwa_files=["assets/src/manifest.json", "assets/src/service-worker.js"],
            copy_files=["assets/src/favicon.ico"],
            minify=True,
            sourcemap=True,
            asset_names="[name]-[hash]",
            entry_names="[name]-[hash]",
            outbase="assets/src",
            extra_esbuild_args=["--loader:.png=file", "--loader:.woff2=file"]
        )

        builder.build()
    """

    def __init__(
        self,
        static_src: str | Path,
        static_dist: str | Path,
        entry_points: list[str | Path],
        *,
        pwa_files: list[str | Path] | None = None,
        copy_files: list[str | Path] | None = None,
        minify: bool = True,
        sourcemap: bool | Literal["external", "inline"] = False,
        asset_names: str = "[dir]/[name]-[hash]",
        entry_names: str = "[dir]/[name]-[hash]",
        outbase: str | Path | None = None,
        bundle: bool = False,
        extra_esbuild_args: list[str] | None = None,
    ):

        self.static_src = Path(static_src).resolve()
        self.static_dist = Path(static_dist).resolve()
        self.entry_points = [Path(ep).resolve() for ep in entry_points]
        self.pwa_files = [Path(pf).resolve() for pf in (pwa_files or [])]
        self.copy_files = [Path(cf).resolve() for cf in (copy_files or [])]
        self.minify = minify
        self.sourcemap = sourcemap
        self.asset_names = asset_names
        self.entry_names = entry_names
        self.bundle = bundle
        self.outbase = Path(outbase).resolve() if outbase else self.static_src
        self.extra_esbuild_args = extra_esbuild_args or []

    def _ensure_dirs(self):
        if self.static_dist.exists() and self.static_dist.is_dir():
            import shutil

            shutil.rmtree(self.static_dist)

        self.static_dist.mkdir(parents=True, exist_ok=True)

    def _build_esbuild_cmd(self) -> list[str]:
        cmd = ["npx", "--yes", "esbuild"]
        cmd.extend(str(ep) for ep in self.entry_points)
        cmd.append(f"--outdir={self.static_dist}")
        cmd.append(f"--outbase={self.outbase}")

        if self.minify:
            cmd.append("--minify")

        if self.sourcemap == True:
            cmd.append("--sourcemap")
        elif self.sourcemap == "external":
            cmd.append("--sourcemap=external")
        elif self.sourcemap == "inline":
            cmd.append("--sourcemap=inline")

        if self.bundle:
            cmd.append("--bundle")

        cmd.append(f"--asset-names={self.asset_names}")
        cmd.append(f"--entry-names={self.entry_names}")
        cmd.append(f"--metafile={self.static_dist / 'meta.json'}")
        cmd.extend(self.extra_esbuild_args)

        return cmd

    def _generate_manifest(self) -> dict:
        meta_path = self.static_dist / "meta.json"
        logger.debug(f"Looking for metafile at: {meta_path}")
        if not meta_path.exists():
            logger.warning(f"Metafile not found at {meta_path}")
            return {}

        with open(meta_path) as f:
            meta = json.load(f)

        logger.debug(f"Loaded metafile with {len(meta.get('outputs', {}))} outputs")

        manifest = {}
        for out, meta_data in meta.get("outputs", {}).items():
            original = meta_data.get("entryPoint")

            if original:
                original_path = Path(original).resolve()
                try:
                    original_name_with_path = original_path.relative_to(self.static_src).as_posix()
                except ValueError:
                    original_name_with_path = original_path.name

                hashed_path = Path(out).resolve()
                try:
                    hashed_name = hashed_path.relative_to(self.static_dist).as_posix()
                except ValueError:
                    hashed_name = hashed_path.name

                manifest[original_name_with_path] = hashed_name
                logger.debug(f"Mapping {original_name_with_path} -> {hashed_name}")

        return manifest

    def _copy_files(self, files: list[Path]):
        import shutil

        for src in files:
            if src.exists():
                dest = self.static_dist / src.relative_to(self.static_src)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dest)
                logger.info(f"Copied {src.relative_to(self.static_src)} to {dest.relative_to(self.static_dist)}")

    def build(self):
        """
        Run the full build process
        """

        try:
            node_check = subprocess.run(["node", "--version"], capture_output=True, text=True)
            if node_check.returncode != 0:
                logger.error("Node.js is not installed or not found in PATH. Please install Node.js to build assets.")
                sys.exit(1)
        except FileNotFoundError:
            logger.error("Node.js is not installed or not found in PATH. Please install Node.js to build assets.")
            sys.exit(1)

        self._ensure_dirs()

        cmd = self._build_esbuild_cmd()
        logger.info("Running build...")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"build failed: {result.stderr}")
            sys.exit(1)

        manifest = self._generate_manifest()
        manifest_path = self.static_dist / "assets.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Manifest written to {manifest_path}")

        self._copy_files(self.pwa_files)
        self._copy_files(self.copy_files)

        meta_path = self.static_dist / "meta.json"
        if meta_path.exists():
            meta_path.unlink()

        logger.info("Build completed successfully.")
