from time import sleep
from unittest.mock import ANY, MagicMock, Mock, patch

from django.conf import settings
import pytest

from pgpubsub.metrics import (
    configure_monitoring,
    queue_length_callback,
    queue_processing_lag_callback,
)
from pgpubsub.models import Notification


_init_opentelemetry_mock = Mock()


def _init_opentelemetry() -> None:
    _init_opentelemetry_mock()


def test_configures_meters_when_initializer_is_set(settings):
    settings.PGPUBSUB_OPENTELEMETRY_INITIALIZER = (
        "pgpubsub.tests.test_metrics._init_opentelemetry"
    )

    with patch("pgpubsub.metrics.metrics") as metrics_api_mock:
        meter_mock = MagicMock()
        metrics_api_mock.get_meter.return_value = meter_mock
        _init_opentelemetry_mock.reset_mock()

        configure_monitoring()

        _init_opentelemetry_mock.assert_called_once()
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


def test_configures_meters_when_no_initializer_configured(settings):
    if hasattr(settings, 'PGPUBSUB_OPENTELEMETRY_INITIALIZER'):
        delattr(settings, 'PGPUBSUB_OPENTELEMETRY_INITIALIZER')

    with patch("pgpubsub.metrics.metrics") as metrics_api_mock:
        meter_mock = MagicMock()
        metrics_api_mock.get_meter.return_value = meter_mock

        configure_monitoring()

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
