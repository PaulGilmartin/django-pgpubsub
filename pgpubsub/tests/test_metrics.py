from time import sleep
from unittest.mock import ANY, MagicMock, patch

from django.conf import settings
from opentelemetry.metrics import MeterProvider
import pytest

from pgpubsub.metrics import (
    configure_monitoring,
    queue_length_callback,
    queue_processing_lag_callback,
    MeterProviderFactory,
)
from pgpubsub.models import Notification


class MockMeterProviderFactory(MeterProviderFactory):
    meter_provider: MeterProvider = None

    def get_meter_provider(self) -> MeterProvider:
        return self.meter_provider


def test_configures_monitoring_using_meter_provider(settings):
    meter_provider = MagicMock()
    MockMeterProviderFactory.meter_provider = meter_provider
    settings.PGPUBSUB_METER_PROVIDER_FACTORY = (
        "pgpubsub.tests.test_metrics.MockMeterProviderFactory"
    )

    with patch("pgpubsub.metrics.metrics") as metrics_api_mock:
        meter_mock = MagicMock()
        metrics_api_mock.get_meter.return_value = meter_mock

        configure_monitoring()

        metrics_api_mock.set_meter_provider.assert_called_once_with(meter_provider)
        metrics_api_mock.get_meter.assert_called()
        meter_mock.create_observable_gauge.assert_any_call(
            name="pgpubsub.notifications-queue.len",
            callbacks=[queue_length_callback],
            description=ANY,
            unit="items",
        )
        meter_mock.create_observable_gauge.assert_any_call(
            name="pgpubsub.notifications-queue.processing-lag",
            callbacks=[queue_processing_lag_callback],
            description=ANY,
            unit="ms",
        )


def test_does_not_configure_monitoring_with_no_setting(settings):
    if hasattr(settings, 'PGPUBSUB_METER_PROVIDER_FACTORY'):
        delattr(settings, 'PGPUBSUB_METER_PROVIDER_FACTORY')
    with patch("opentelemetry.metrics.set_meter_provider") as set_meter_provider_mock:
        configure_monitoring()
        set_meter_provider_mock.assert_not_called()


@pytest.mark.django_db
def test_queue_length_callback_returns_queue_len():
    observations = list(queue_length_callback(MagicMock()))
    assert observations[0].value == 0

    Notification.objects.create(channel="pgpubsub_a83de", payload='{}')
    Notification.objects.create(channel="pgpubsub_a83de", payload='{}')

    observations = list(queue_length_callback(MagicMock()))
    assert observations[0].value == 2


@pytest.mark.django_db
def test_queue_processing_lag_callback_returns_lag():
    observations = list(queue_processing_lag_callback(MagicMock()))
    assert observations[0].value == 0

    Notification.objects.create(channel="pgpubsub_a83de", payload='{}')
    sleep(0.05)
    Notification.objects.create(channel="pgpubsub_a83de", payload='{}')
    sleep(0.05)

    observations = list(queue_processing_lag_callback(MagicMock()))
    assert observations[0].value >= 100
