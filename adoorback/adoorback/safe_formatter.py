import logging

class SafeFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, 'username'):
            record.username = 'N/A'
        if not hasattr(record, 'token'):
            record.token = 'N/A'
        return super().format(record)
