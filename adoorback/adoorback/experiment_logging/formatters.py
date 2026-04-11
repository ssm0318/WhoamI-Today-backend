import logging


class JSONExperimentFormatter(logging.Formatter):
    """Formatter that outputs the log message as-is.

    The middleware already produces a JSON string, so this formatter
    simply passes it through without adding any extra formatting.
    """

    def format(self, record):
        return record.getMessage()
