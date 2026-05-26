from typing import Any

from lib.monitoring.prometheus.schemas import PrometheusMetricsConfig


class MetricsRegistry:
    """
    A registry for storing Prometheus metrics and configuration.

    This is a simple wrapper around a dictionary that allows us to store
    metrics by name and retrieve them later. It also allows us to store
    a global configuration object for metrics.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, Any] = {}
        self._config: PrometheusMetricsConfig | None = None

    def set_config(self, config: PrometheusMetricsConfig) -> None:
        self._config = config

    @property
    def config(self) -> PrometheusMetricsConfig | None:
        return self._config

    def register(self, name: str, metric: Any) -> Any:
        """
        Store a metric by name so it can be retrieved later.
        """
        if name in self._metrics:
            return self._metrics[name]

        self._metrics[name] = metric
        return metric

    def get(self, name: str) -> Any | None:
        return self._metrics.get(name)

    def all(self) -> dict[str, Any]:
        return dict(self._metrics)

    def __repr__(self) -> str:
        names = list(self._metrics.keys())
        return f"<MetricsRegistry metrics={names}>"


metrics_registry = MetricsRegistry()
