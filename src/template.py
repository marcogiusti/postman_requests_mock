import re as _re
from string import Formatter


class PostmanFormatter(Formatter):

    pattern = _re.compile(
        r'''
        (?:
          {{(?P<field_name>[_a-zA-Z0-9]+)}}
        )
        ''',
        _re.VERBOSE
    )

    def parse(self, format_string):
        if not format_string:
            return
        begin = 0
        for match in self.pattern.finditer(format_string):
            literal_text = format_string[begin:match.start()]
            field_name = match.group('field_name')
            format_spec = 's'  # or just the empty string ''
            conversion = None  # XXX: maybe 's'?
            yield literal_text, field_name, format_spec, conversion
            begin = match.end()

    def get_field(self, field_name, args, kwargs):
        obj = kwargs[field_name]
        return obj, field_name

    def convert_field(self, value, conversion):
        return value  # ignore conversion

    def format_field(self, value, format_spec):
        return value  # ignore field formatting
