import os
import tempfile
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from prometheus_client import CollectorRegistry, multiprocess
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator import metrics as pfi_metrics

from lib.logger import get_logger
from lib.monitoring.prometheus.registry import metrics_registry
from lib.monitoring.prometheus.schemas import PrometheusMetricsConfig

logger = get_logger("lib.monitoring.prometheus.config")


_DEFAULT_CONFIG = PrometheusMetricsConfig()


def _ensure_prometheus_multiproc_dir(app_name: str) -> str:
    env_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if env_dir:
        if not os.path.isdir(env_dir):
            os.makedirs(env_dir, exist_ok=True)
            logger.warning(
                f"PROMETHEUS_MULTIPROC_DIR is set to {env_dir} but did not exist; created it.",
            )

        return env_dir

    default_dir = os.path.join(tempfile.gettempdir(), f"{app_name}_prometheus_multiproc")
    os.makedirs(default_dir, exist_ok=True)

    sentinel_path = os.path.join(default_dir, f".{app_name}_prometheus_multiproc_initialized")
    if not os.path.exists(sentinel_path):
        logger.warning(
            f"PROMETHEUS_MULTIPROC_DIR was not set; auto-created {default_dir}."
            "For multi-process metrics, set PROMETHEUS_MULTIPROC_DIR explicitly to a shared writable directory.",
        )

        with open(sentinel_path, "w", encoding="utf-8") as sentinel_file:
            sentinel_file.write("initialized\n")

    os.environ["PROMETHEUS_MULTIPROC_DIR"] = default_dir
    return default_dir


def configure_prometheus(
    app: FastAPI,
    config: PrometheusMetricsConfig | None = None,
) -> Instrumentator:
    """Instrument *app* with Prometheus metrics.

    Parameters
    ----------
    app:
        The FastAPI application instance to instrument.
    config:
        A :class:`PrometheusMetricsConfig` instance.  When
        omitted a sensible default config is used.
    Returns
    -------
    Instrumentator
        The configured instrumentator in case you need further customisation.
    """

    cfg = config or _DEFAULT_CONFIG
    metrics_registry.set_config(cfg)

    if cfg.multiprocess_mode and not cfg.registry:
        _ensure_prometheus_multiproc_dir(cfg.app_name)
        cfg.registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(cfg.registry)

    for metric in cfg.custom_metrics:
        name = getattr(metric, "_name", None) or str(metric)
        metrics_registry.register(name, metric)

    instrumentator_kwargs: dict[str, Any] = {
        "should_group_status_codes": cfg.should_group_status_codes,
        "should_ignore_untemplated": cfg.should_ignore_untemplated,
        "should_group_untemplated": cfg.should_group_untemplated,
        "excluded_handlers": cfg.excluded_handlers,
    }

    if cfg.registry:
        instrumentator_kwargs["registry"] = cfg.registry

    instrumentator = Instrumentator(**instrumentator_kwargs)

    default_metric_kwargs: dict = {}
    if cfg.namespace:
        default_metric_kwargs["metric_namespace"] = cfg.namespace
    if cfg.subsystem:
        default_metric_kwargs["metric_subsystem"] = cfg.subsystem
    if cfg.latency_buckets:
        default_metric_kwargs["latency_highr_buckets"] = cfg.latency_buckets
    if cfg.include_app_name_label:
        default_metric_kwargs["custom_labels"] = {"app": cfg.app_name}
    if cfg.registry:
        default_metric_kwargs["registry"] = cfg.registry

    instrumentator.add(pfi_metrics.default(**default_metric_kwargs))

    instrumentator.instrument(app)

    _attach_lifespan_expose(app, instrumentator, cfg)

    logger.info(
        f"Metrics configured for '{cfg.app_name}' mapped to {cfg.metrics_endpoint}",
    )

    return instrumentator


def _attach_lifespan_expose(
    app: FastAPI,
    instrumentator: Instrumentator,
    cfg: PrometheusMetricsConfig,
) -> None:
    """
    Attach the instrumentator.expose call to the app's lifespan context,
    ensuring that the metrics endpoint is properly set up when the app starts and that any necessary cleanup is performed when the app shuts down.

    This is especially important in multiprocess mode to mark the process as dead when it shuts down, preventing stale metrics from being exposed.
    """

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def _metrics_lifespan(app: FastAPI) -> AsyncIterator[None]:
        instrumentator.expose(
            app,
            endpoint=cfg.metrics_endpoint,
            include_in_schema=cfg.include_in_schema,
            should_gzip=cfg.should_gzip,
        )

        try:
            if original_lifespan is not None:
                async with original_lifespan(app):
                    yield
            else:
                yield
        finally:
            if cfg.multiprocess_mode and "PROMETHEUS_MULTIPROC_DIR" in os.environ:
                multiprocess.mark_process_dead(os.getpid())

    app.router.lifespan_context = _metrics_lifespan
