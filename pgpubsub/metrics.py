from typing import Any, Generator, Protocol

from django.conf import settings
from django.db.models import Min
from django.utils import timezone
from opentelemetry import metrics


class OpentelemetryInitializer(Protocol):
    def __call__() -> None:
        ...


def queue_length_callback(options: Any) -> Generator[metrics.Observation, None, None]:
    from pgpubsub.models import Notification

    yield metrics.Observation(Notification.objects.all().count())


def queue_processing_lag_callback(options: Any) -> Generator[metrics.Observation, None, None]:
    from pgpubsub.models import Notification

    min_created_at = Notification.objects.aggregate(Min('created_at'))['created_at__min']

    if min_created_at is None:
        lag_ms = 0
    else:
        time_difference = timezone.now() - min_created_at
        lag_ms = time_difference.total_seconds() * 1000

    yield metrics.Observation(lag_ms)


def _metric_name(name: str) -> str:
    prefix = getattr(settings, "PGPUBSUB_METRIC_PREFIX", "pgpubsub")
    return f"{prefix}.{name}"


def _create_instruments(meter: metrics.Meter) -> None:
    meter.create_observable_gauge(
        name=_metric_name("notifications-queue.len"),
        callbacks=[queue_length_callback],
        description="Notifications queue length",
        unit="items",
    )
    meter.create_observable_gauge(
        name=_metric_name("notifications-queue.processing-lag"),
        callbacks=[queue_processing_lag_callback],
        description="Notifications queue processing lag",
        unit="ms",
    )


def configure_monitoring():
    opentelemetry_initializer_func_qname: str | None = getattr(
        settings, "PGPUBSUB_OPENTELEMETRY_INITIALIZER", None
    )
    if opentelemetry_initializer_func_qname:
        module_name, func_name = opentelemetry_initializer_func_qname.rsplit(".", 1)
        opentelemetry_init: OpentelemetryInitializer = getattr(
            __import__(module_name, fromlist=[func_name]), func_name
        )
        opentelemetry_init()

    meter: metrics.Meter = metrics.get_meter(__name__)

    _create_instruments(meter)
