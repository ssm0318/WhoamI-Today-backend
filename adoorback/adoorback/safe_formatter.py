import logging

class SafeFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, 'username'):
            record.username = 'N/A'
        if not hasattr(record, 'token'):
            record.token = 'N/A'
        if not hasattr(record, 'user_id'):
            record.user_id = ''
        if not hasattr(record, 'page'):
            record.page = 'N/A'
        if not hasattr(record, 'body'):
            record.body = ''
        if not hasattr(record, 'os'):
            record.os = 'N/A'
        return super().format(record)
