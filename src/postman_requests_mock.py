from collections import ChainMap
from collections.abc import MutableMapping
import io
import json
import random
import re
from string import Formatter
import time
from urllib.parse import urlparse, urlunparse
import uuid

import responses
from urllib3.response import HTTPResponse


__version__ = '0.1.0'
__all__ = [
    # constants
    'V21_SCHEMA_URL',
    # High level interface
    'load_scope', 'load_scope_from_file', 'requests_mock',
    'PostmanCollectionV21',
    # low level classes
    'ItemV21', 'StringRequestV21', 'RequestV21', 'ResponseV21',
    'PostmanResponseV21',
    # misc
    'PostmanFormatter'
]


V21_SCHEMA_URL = (
    'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'
)


def normalize_lowercase(key):
    return key.lower() if isinstance(key, str) else key


class NormalizedDict(MutableMapping):

    __slots__ = 'data'

    def __init__(self, arg=None, **kwds):
        self.data = {}
        if arg is not None:
            self.update(arg, **kwds)
        else:
            self.update(kwds)

    def __setitem__(self, key, value):
        self.data[self.normalize(key)] = value

    def __getitem__(self, key):
        return self.data[self.normalize(key)]

    def __delitem__(self, key):
        del self.data[self.normalize(key)]

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        itemfmt = '{0[0]!r}: {0[1]!r}'
        parts = (itemfmt.format(item) for item in self.items())
        return '{' + ', '.join(parts) + '}'


class CaseInsensitivesDict(NormalizedDict):

    def normalize(self, key):
        return normalize_lowercase(key)


class PostmanFormatter(Formatter):

    pattern = re.compile(
        r'''
        (?:
          {{\s*(?P<field_name>\$?[_a-zA-Z0-9]+)\s*}}
        )
        ''',
        re.VERBOSE
    )

    def parse(self, format_string):
        if not format_string:
            return
        begin = 0
        for match in self.pattern.finditer(format_string):
            literal_text = format_string[begin:match.start()]
            field_name = match.group('field_name')
            # literal_text, field_name, format_spec, conversion
            yield literal_text, field_name, '', 's'
            begin = match.end()
        yield format_string[begin:], None, '', None

    def get_field(self, field_name, args, kwargs):
        if field_name == '$guid':
            ret = uuid.uuid4()
        elif field_name == '$timestamp':
            ret = time.time()
        elif field_name == '$randomInt':
            ret = random.randint(0, 1000)
        else:
            try:
                ret = kwargs[field_name]
            except KeyError:
                ret = '{{%s}}' % field_name
        return ret, field_name

    def format_field(self, value, format_spec):
        return value  # ignore field formatting


def load_scope(varlist):
    return {
        var['key']: var['value'] for var in varlist
        if 'key' in var and 'value' in var and var.get('enabled', True)
    }


def load_scope_from_file(filename):
    with open(filename, encoding='utf-8') as fp:
        return load_scope(json.load(fp).get('values', []))


_formatter = PostmanFormatter()


class PostmanCollectionV21:

    _schema = None

    @classmethod
    def from_file(cls, filename, global_scope={}, environment={},
                  validate=None):
        with open(filename, encoding='utf-8') as fp:
            return cls(json.load(fp), global_scope, environment, validate)

    def __init__(self, collection, global_scope={}, environment={},
                 validate=None):
        if validate is not None:
            validate(collection)
        self._collection = collection
        self._global = global_scope
        self._environment = environment

    def _variables(self):
        return load_scope(self._collection.get('variable', []))

    def expand(self, string):
        scopes = ChainMap(self._environment, self._variables(), self._global)
        return _formatter.vformat(string, (), scopes)

    def _iter_items(self, group):
        for item in group['item']:
            if 'item' in item:
                yield from self._iter_items(item)
            else:
                yield ItemV21(item, self)

    def items(self):
        yield from self._iter_items(self._collection)

    def responses(self):
        for item in self.items():
            yield from item.responses()


class ItemV21:

    def __init__(self, item, collection):
        self._item = item
        self._collection = collection

    def request(self):
        request = self._item['request']
        if isinstance(request, str):
            return StringRequestV21(request, self._collection)
        return RequestV21(request, self._collection)

    def responses(self):
        request = self.request()
        for response in self._item.get('response', []):
            if not isinstance(response, str):
                yield ResponseV21(request, response, self._collection)


class StringRequestV21:

    def __init__(self, url, collection):
        self._url = url
        self._collection = collection

    def expand(self, string):
        return self._collection.expand(string)

    def method(self):
        return 'GET'

    def _urlparse(self):
        url = self.expand(self._url)
        return urlparse(url, scheme='http')

    def url(self):
        return self._urlparse().geturl()

    def headers(self):
        return {}

    def auth(self):
        parsed = self._urlparse()
        if parsed.username is not None and parsed.password is not None:
            return parsed.username, parsed.password


class RequestV21:

    def __init__(self, original, collection):
        self._original = original
        self._collection = collection

    def expand(self, string):
        return self._collection.expand(string)

    def method(self):
        return self._original['method']

    def url(self):
        url = self._original['url']
        if isinstance(url, str):
            return urlparse(self.expand(url), scheme='http').geturl()
        scheme = url.get('protocol', 'http')
        netloc = url['host']
        if not isinstance(url['host'], str):
            netloc = '.'.join(url['host'])
        if 'port' in url:
            netloc += ':' + url['port']
        variables = {v['key']: v['value'] for v in url.get('variable', [])}
        # a first empty element assures that the path will start with slash
        if 'path' in url:
            path = url['path']
            if isinstance(path, str):
                path = filter(None, path.split('/'))
            parts = ['']
            for part in path:
                if part.startswith(':'):
                    part = variables.get(part[1:], part)
                parts.append(part)
            path = '/'.join(parts)
        else:
            path = ''
        params = ''
        query = ''
        fragment = url.get('hash', '')
        url = urlunparse((scheme, netloc, path, params, query, fragment))
        return self.expand(url)

    def headers(self):
        return {
            self.expand(h['key']): self.expand(h['value'])
            for h in self._original['header']
        }

    def auth(self):
        auth = self._original.get('auth')
        if auth is None:
            return
        atype = auth['type']
        if atype == 'basic':
            args = {i['key']: i['value'] for i in auth['basic']}
            return (args['username'], args['password'])


class ResponseV21:

    def __init__(self, request, response, collection):
        self._request = request
        self._response = response
        self._collection = collection

    def request(self):
        return self._request

    def code(self):
        return self._response['code']

    def status(self):
        return self._response['status']

    def body(self):
        return self._response['body']

    def headers(self):
        return {h['key']: h['value'] for h in self._response['header']}


class PostmanResponseV21(responses.BaseResponse):

    def __init__(self, response, match_querystring=True):
        self._response = response
        request = response.request()
        super().__init__(request.method(), request.url(), match_querystring)

    def get_response(self, request):
        res = self._response
        return HTTPResponse(
            body=io.BytesIO(res.body().encode('utf-8')),
            headers=res.headers(),
            status=res.code(),
            reason=res.status(),
            preload_content=False
        )

    def matches(self, request):
        if not super().matches(request):
            return False
        original = self._response.request()
        headers = CaseInsensitivesDict(request.headers)
        for key, value in original.headers().items():
            if headers.get(key) != value:
                return False
        req_c = request.copy()
        auth = original.auth()
        if auth is not None:
            req_c.prepare_auth(auth)
            # TODO: what to check?
            if (req_c.headers, req_c.body) != (request.headers, request.body):
                return False
        return True


def requests_mock(collection, **kwds):
    mock = responses.RequestsMock(**kwds)
    for response in collection.responses():
        mock.add(PostmanResponseV21(response))
    return mock
