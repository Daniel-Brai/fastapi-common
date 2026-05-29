from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Union

from prometheus_client import CollectorRegistry
from prometheus_client.registry import Collector


@dataclass
class PrometheusMetricsConfig:
    """
    Configuration for Prometheus metrics instrumentation.

    Parameters
    ----------
    app_name:
        Human-readable service name — attached as a default label when
        ``include_app_name_label`` is True.
    namespace:
        Prefix namespace for all auto-instrumented metrics
        (e.g. ``"myorg"`` → ``myorg_api_http_requests_total``).
    subsystem:
        Subsystem prefix appended after namespace.
    metrics_endpoint:
        Path at which Prometheus scrapes metrics.  Defaults to ``"/metrics"``.
    include_in_schema:
        Whether to include the metrics endpoint in the OpenAPI docs.
    should_gzip:
        Compress the /metrics response with gzip when the client supports it.
    excluded_handlers:
        List of route paths that will **not** be instrumented
        (e.g. health-check endpoints).
    should_group_status_codes:
        Group status codes into 2xx / 3xx etc. instead of per-code.
    should_ignore_untemplated:
        Ignore requests that do not match a templated route.
    should_group_untemplated:
        Group all untemplated routes under a single label.
    latency_buckets:
        Custom histogram buckets for latency metrics (seconds).
        Defaults to Prometheus' standard buckets.
    multiprocess_mode:
        Set to True when running under a multi-process server
        (e.g. gunicorn with multiple workers).  Requires the
        ``PROMETHEUS_MULTIPROC_DIR`` env variable to point to a shared
        writable directory.
    registry:
        Custom CollectorRegistry.  Defaults to the global REGISTRY.
    custom_metrics:
        Extra ``prometheus_client`` metric objects you want to register /
        track alongside the auto-instrumented ones.  They are **not**
        collected automatically — you still need to call ``.inc()`` /
        ``.observe()`` etc. in your business logic.  Listing them here
        makes them visible in ``metrics_registry`` and in the docs.
    include_app_name_label:
        When True, an ``app`` label equal to ``app_name`` is added to
        every auto-instrumented metric.
    """

    app_name: str = "fastapi-app"
    namespace: str = ""
    subsystem: str = ""

    metrics_endpoint: str = "/metrics"
    include_in_schema: bool = False
    should_gzip: bool = True

    excluded_handlers: List[str] = field(default_factory=list)
    should_group_status_codes: bool = True
    should_ignore_untemplated: bool = True
    should_group_untemplated: bool = True

    latency_buckets: Optional[Sequence[Union[float, str]]] = None

    multiprocess_mode: bool = False
    registry: Optional[CollectorRegistry] = None

    custom_metrics: List[Collector] = field(default_factory=list)
    include_app_name_label: bool = False
