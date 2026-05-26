from typing import Literal, Sequence

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Enum, Gauge, Histogram, Info, Summary

from lib.monitoring.prometheus.registry import metrics_registry


def _resolve_registry(registry: CollectorRegistry | None) -> CollectorRegistry:
    cfg = metrics_registry.config
    if registry is not None:
        return registry

    if cfg and cfg.registry:
        return cfg.registry

    return REGISTRY


def _build_name(name: str, namespace: str = "", subsystem: str = "") -> str:
    """
    Prepend namespace or subsystem when not already present in ``name``.
    """

    cfg = metrics_registry.config
    ns = namespace or (cfg.namespace if cfg else "")
    sub = subsystem or (cfg.subsystem if cfg else "")
    parts = [p for p in [ns, sub, name] if p]
    return "_".join(parts)


def counter(
    name: str,
    documentation: str,
    labels: list[str] | None = None,
    namespace: str = "",
    subsystem: str = "",
    registry: CollectorRegistry | None = None,
) -> Counter:
    """
    Create (or retrieve) a :class:`prometheus_client.Counter`.

    Parameters
    ----------
    name:
        Metric name.  Namespace/subsystem from :class:`MetricsConfig` are
        prepended automatically unless already present.
    documentation:
        Help text shown in the /metrics output.
    labels:
        List of label names (``labelnames`` in prometheus_client).
    namespace / subsystem:
        Override the global namespace/subsystem for this metric only.
    registry:
        Override the global registry for this metric only.

    Returns
    -------
    Counter
        The created (or previously registered) Counter object.
    """

    full_name = _build_name(name, namespace, subsystem)
    existing = metrics_registry.get(full_name)
    if existing is not None:
        return existing  # type: ignore[return-value]

    metric = Counter(
        full_name,
        documentation,
        labelnames=labels or [],
        registry=_resolve_registry(registry),
    )
    metrics_registry.register(full_name, metric)
    return metric


def histogram(
    name: str,
    documentation: str,
    labels: list[str] | None = None,
    buckets: Sequence[float | str] | None = None,
    namespace: str = "",
    subsystem: str = "",
    registry: CollectorRegistry | None = None,
) -> Histogram:
    """
    Create (or retrieve) a :class:`prometheus_client.Histogram`.

    Parameters
    ----------
    buckets:
        Observation bucket boundaries.  Falls back to MetricsConfig
        ``latency_buckets`` then to Prometheus' default buckets.
    """

    full_name = _build_name(name, namespace, subsystem)
    existing = metrics_registry.get(full_name)
    if existing is not None:
        return existing  # type: ignore[return-value]

    cfg = metrics_registry.config
    resolved_buckets = buckets or (cfg.latency_buckets if cfg else None) or Histogram.DEFAULT_BUCKETS

    metric = Histogram(
        full_name,
        documentation,
        labelnames=labels or [],
        buckets=resolved_buckets,
        registry=_resolve_registry(registry),
    )
    metrics_registry.register(full_name, metric)
    return metric


def gauge(
    name: str,
    documentation: str,
    labels: list[str] | None = None,
    multiprocess_mode: Literal[
        "all",
        "liveall",
        "min",
        "livemin",
        "max",
        "livemax",
        "sum",
        "livesum",
        "mostrecent",
        "livemostrecent",
    ] = "all",
    namespace: str = "",
    subsystem: str = "",
    registry: CollectorRegistry | None = None,
) -> Gauge:
    """
    Create (or retrieve) a :class:`prometheus_client.Gauge`.

    Parameters
    ----------
    multiprocess_mode:
        One of ``"all"``, ``"liveall"``, ``"min"``, ``"livemin"``,
        ``"max"``, ``"livemax"``, ``"sum"``, ``"livesum"``.
        Relevant only in multi-process mode.

    """
    full_name = _build_name(name, namespace, subsystem)
    existing = metrics_registry.get(full_name)
    if existing is not None:
        return existing  # type: ignore[return-value]

    metric = Gauge(
        full_name,
        documentation,
        labelnames=labels or [],
        multiprocess_mode=multiprocess_mode,
        registry=_resolve_registry(registry),
    )
    metrics_registry.register(full_name, metric)
    return metric


def summary(
    name: str,
    documentation: str,
    labels: list[str] | None = None,
    namespace: str = "",
    subsystem: str = "",
    registry: CollectorRegistry | None = None,
) -> Summary:
    """
    Create (or retrieve) a :class:`prometheus_client.Summary`.
    """

    full_name = _build_name(name, namespace, subsystem)
    existing = metrics_registry.get(full_name)
    if existing is not None:
        return existing  # type: ignore[return-value]

    metric = Summary(
        full_name,
        documentation,
        labelnames=labels or [],
        registry=_resolve_registry(registry),
    )
    metrics_registry.register(full_name, metric)
    return metric


def info(
    name: str,
    documentation: str,
    namespace: str = "",
    subsystem: str = "",
    registry: CollectorRegistry | None = None,
) -> Info:
    """
    Create (or retrieve) a :class:`prometheus_client.Info`.

    Info gauges expose a set of static key/value pairs (e.g. app version).

    Example
    -------
        APP_INFO = info("app_info", "Application metadata")
        APP_INFO.info({"version": "1.2.3", "env": "production"})
    """

    full_name = _build_name(name, namespace, subsystem)
    existing = metrics_registry.get(full_name)
    if existing is not None:
        return existing  # type: ignore[return-value]

    metric = Info(
        full_name,
        documentation,
        registry=_resolve_registry(registry),
    )
    metrics_registry.register(full_name, metric)
    return metric


def enum(
    name: str,
    documentation: str,
    states: list[str],
    labels: list[str] | None = None,
    namespace: str = "",
    subsystem: str = "",
    registry: CollectorRegistry | None = None,
) -> Enum:
    """
    Create (or retrieve) a :class:`prometheus_client.Enum`.

    Example
    -------
        TASK_STATE = enum(
            "worker_task_state",
            "Current state of the background worker",
            states=["idle", "running", "error"],
        )
        TASK_STATE.state("running")
    """

    full_name = _build_name(name, namespace, subsystem)
    existing = metrics_registry.get(full_name)
    if existing is not None:
        return existing  # type: ignore[return-value]

    metric = Enum(
        full_name,
        documentation,
        labelnames=labels or [],
        states=states,
        registry=_resolve_registry(registry),
    )
    metrics_registry.register(full_name, metric)
    return metric
