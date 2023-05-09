from typing import Any, Generator, Protocol

from django.conf import settings
from django.db.models import Min
from django.utils import timezone
from opentelemetry import metrics

from pgpubsub.models import Notification


class MeterProviderFactory(Protocol):
    def get_meter_provider() -> metrics.MeterProvider:
        ...


def queue_length_callback(options: Any) -> Generator[metrics.Observation, None, None]:
    yield metrics.Observation(Notification.objects.all().count())


def queue_processing_lag_callback(options: Any) -> Generator[metrics.Observation, None, None]:
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
    meter_provider_factory_classname: str = getattr(
        settings, "PGPUBSUB_METER_PROVIDER_FACTORY", None
    )
    if meter_provider_factory_classname:
        module_name, class_name = meter_provider_factory_classname.rsplit(".", 1)
        MeterProviderFactoryClass: Type[MeterProviderFactory] = getattr(
            __import__(module_name, fromlist=[class_name]), class_name
        )
        meter_provider_factory: MeterProviderFactory = MeterProviderFactoryClass()
        meter_provider = meter_provider_factory.get_meter_provider()
        metrics.set_meter_provider(meter_provider)

        meter: mertric.Meter = metrics.get_meter(__name__)

        _create_instruments(meter)
