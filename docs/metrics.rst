.. _metrics:

Exporting Metrics
=================

To facilitate the listener process monitoring several metrics can be exported via
[opentelementry API](https://opentelemetry.io/) using ``monitor_listener`` command:

- ``notifications-queue.len``: the length of the notification queue, that is
  the number of unprocessed notifications stored in the DB
- ``notifications-queue.processing-lag``: the age (in the milliseconds) of the
  oldest unprocessed notification.

Do to that implement ``MeterProviderFactory``. Here's the example of the console
exporter:

.. code-block:: python

    # some/path/mymeter.py
   
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
   
    from pgpubsub.metrics import MeterProviderFactory
  
    
    class TestMeterProviderFactory(MeterProviderFactory):
        def get_meter_provider(self) -> MeterProvider:
            exporter = ConsoleMetricExporter()
            reader = PeriodicExportingMetricReader(
                exporter,
                export_interval_millis=5_000,
            )
            return MeterProvider(metric_readers=[reader])

You'll need to add ``opentelemetry-sdk`` package to you project.

Then specify that this factory should be used by ``pgpubsub`` to export
metrics in django settings:

.. code-block:: python

    # package together with classname should be specified
    PGPUBSUB_METER_PROVIDER_FACTORY = "some.path.mymeter.TestMeterProviderFactory"
    # this allows to configure metrics prefix
    PGPUBSUB_METRIC_PREFIX = "myapp-metrics"
