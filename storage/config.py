from libcloud.storage.base import StorageDriver
from libcloud.storage.providers import get_driver
from libcloud.storage.types import Provider
from sqlalchemy_file.storage import StorageManager


def configure_storage(
    provider: str | Provider = "LOCAL",
    *,
    name: str | None = None,
    key_or_path: str = "./uploads",
    secret: str = "",
    container: str = "attachments",
    **kwargs,
) -> None:
    """
    Configure the global StorageManager used by every FileField column.

    Example::

        # Local dev (default):
        configure_storage()

        # S3:
        configure_storage(
            provider  = "S3",
            key       = AWS_ACCESS_KEY_ID,
            secret    = AWS_SECRET_ACCESS_KEY,
            container = "my-s3-bucket",
            region    = "us-east-1",  # optional, defaults to "us-east-1"
        )

        # GCS:
        configure_storage(
            provider  = "GOOGLE_STORAGE",
            key       = GCS_KEY,
            secret    = GCS_SECRET,
            container = "my-gcs-bucket",
            region    = "us-central1",  # optional, defaults to "us"
        )

        # Cloudinary:
        configure_storage(
            provider  = "CLOUDINARY",
            key       = CLOUDINARY_API_KEY,
            secret    = CLOUDINARY_API_SECRET,
            container = "my-cloudinary-folder",
            cloud_name = CLOUDINARY_CLOUD_NAME,
        )
    """

    provider_value: Provider | None = (
        getattr(Provider, provider.upper(), None) if isinstance(provider, str) else provider
    )

    if not provider_value:
        raise ValueError(f"Unsupported storage provider: {provider}")

    driver_cls: type[StorageDriver] = get_driver(provider_value)
    if not driver_cls:
        raise ValueError(f"No driver found for provider: {provider}")

    if provider_value == getattr(Provider, "LOCAL", "local"):
        import pathlib

        path = pathlib.Path(key_or_path)

        if not path.exists():
            path.mkdir(parents=True, mode=0o755, exist_ok=True)

        driver = driver_cls(key_or_path)
    else:
        driver = driver_cls(key_or_path, secret, **kwargs)

    storage_name = name or container

    try:
        StorageManager.get(storage_name)
        return
    except RuntimeError:
        pass

    try:
        container_obj = driver.get_container(container_name=container)
    except Exception:
        container_obj = driver.create_container(container_name=container)

    StorageManager.add_storage(storage_name, container_obj)


def configure_storages(
    storages: dict[str, dict],
    *,
    default: str | None = None,
) -> None:
    """
    Configure multiple storages in one call.

    Example::

        configure_storages({
            "default": {
                "provider": "LOCAL",
                "key": "./uploads",
            },
            "documents": {
                "provider": "S3",
                "key": AWS_ACCESS_KEY_ID,
                "secret": AWS_SECRET_ACCESS_KEY,
                "container": "my-docs-bucket",
                "base_url": "https://my-docs-bucket.s3.amazonaws.com",
            },
            "private": {
                "provider": "S3",
                "key": AWS_ACCESS_KEY_ID,
                "secret": AWS_SECRET_ACCESS_KEY,
                "container": "my-private-bucket",
            },
        }, default="default")
    """

    for name, cfg in storages.items():
        if not isinstance(cfg, dict):
            raise TypeError("Storage configuration must be a dict")

        config = dict(cfg)
        if "key" in config:
            if "key_or_path" in config:
                raise ValueError("storage config may not define both key and key_or_path")
            config["key_or_path"] = config.pop("key")

        configure_storage(
            provider=config.pop("provider", "LOCAL"),
            name=name,
            **config,
        )

    if default:
        StorageManager.set_default(default)
