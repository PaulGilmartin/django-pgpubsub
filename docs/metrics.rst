.. _metrics:

Exporting Metrics
=================

To facilitate the listener process monitoring several metrics can be exported via
[opentelementry API](https://opentelemetry.io/) using ``monitor_listener`` command:

- ``notifications-queue.len``: the length of the notification queue, that is
  the number of unprocessed notifications stored in the DB
- ``notifications-queue.processing-lag``: the age (in the milliseconds) of the
  oldest unprocessed notification.

To do that implement a function that would configure an opentelemetry meter provider.
Here's an example with the console exporter:

.. code-block:: python

    # some/path/my_opentelemetry_init.py

    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader


    def initialize_opentelemetry() -> None:
        exporter = ConsoleMetricExporter()
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=5_000,
        )
        meter_provider = MeterProvider(metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)

You'll need to add ``opentelemetry-sdk`` package to your project.

Then specify that this function should be used by ``pgpubsub`` to initialize
opentelemetry in django settings:

.. code-block:: python

    # import path together with the function name should be specified
    PGPUBSUB_OPENTELEMETRY_INITIALIZER = "some.path.my_opentelemetry_init.initialize_opentelemetry"
    # this allows to configure metrics prefix
    PGPUBSUB_METRIC_PREFIX = "myapp-metrics"
