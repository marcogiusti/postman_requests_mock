from collections.abc import MutableMapping
import io
import json
from urllib.parse import urlparse

import jsonschema
from jsonschema.exceptions import ValidationError
import requests
import responses
from urllib3.response import HTTPResponse


__version__ = '0.0.1'
__all__ = [
    'PostmanCollectionV21', 'PostmanResponseV21', 'ValidationError',
    'requests_mock'
]
V21_SCHEMA_URL = 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'


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


class CaseInsensitivesDict(NormalizedDict):

    def normalize(self, key):
        return normalize_lowercase(key)


class PostmanCollectionV21:

    _schema = None

    @classmethod
    def from_file(cls, filename, validate=True):
        with open(filename, encoding='utf-8') as fp:
            return cls(json.load(fp), validate)

    def __init__(self, collection, validate=True):
        if validate:
            jsonschema.validate(collection, self._get_schema())
        self._collection = collection

    @classmethod
    def _get_schema(cls):
        if cls._schema is None:
            cls._schema = requests.get(V21_SCHEMA_URL).json()
        return cls._schema

    def _iter_items(self, group):
        for item in group['item']:
            if 'item' in item:
                yield from self._iter_items(item)
            else:
                yield ItemV21(item)

    def items(self):
        yield from self._iter_items(self._collection)

    def responses(self):
        for item in self.items():
            yield from item.responses()


class ItemV21:

    def __init__(self, item):
        self._item = item

    def request(self):
        request = self._item['request']
        if isinstance(request, str):
            return StringRequestV21(request)
        return RequestV21(request)

    def responses(self):
        request = self.request()
        for response in self._item.get('response', []):
            if not isinstance(response, str):
                yield ResponseV21(request, response)


class StringRequestV21:

    def __init__(self, url):
        self._url = url

    def method(self):
        return 'GET'

    def url(self):
        return urlparse(self._url, scheme='http').geturl()

    def headers(self):
        return {}

    def auth(self):
        parsed = urlparse(self._url, scheme='http')
        if parsed.username is not None and parsed.password is not None:
            return parsed.username, parsed.password


class RequestV21:

    def __init__(self, original):
        self._original = original

    def method(self):
        return self._original['method']

    def url(self):
        url = self._original['url']
        if isinstance(url, dict):
            url = url['raw']
        # Postman omits the scheme part if not explicited in the original
        # request
        return urlparse(url, scheme='http').geturl()

    def headers(self):
        return {h['key']: h['value'] for h in self._original['header']}

    def auth(self):
        auth = self._original.get('auth')
        if auth is None:
            return
        atype = auth['type']
        if atype == 'basic':
            args = {i['key']: i['value'] for i in auth['basic']}
            return (args['username'], args['password'])


class ResponseV21:

    def __init__(self, request, response):
        self._request = request
        self._response = response

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
        # auth = self._request.get('auth')
        # if auth:
        #     import pdb; pdb.set_trace()
        return True


def requests_mock(collection, **kwds):
    mock = responses.RequestsMock(**kwds)
    for response in collection.responses():
        mock.add(PostmanResponseV21(response))
    return mock
