import json
from os.path import dirname, join as joinpath
import unittest
from postman_requests_mock import (
    PostmanCollectionV21 as _PostmanCollectionV21, ValidationError,
    CaseInsensitivesDict, requests_mock
)
import requests
from requests.exceptions import ConnectionError


def fixture(name):
    return joinpath(dirname(__file__), name)


class PostmanCollectionV21(_PostmanCollectionV21):

    # load the cached version of the schema to speed up the tests and
    # avoid network communication
    with open(fixture('collection.json'), encoding='utf8') as fp:
        _schema = json.load(fp)

    @classmethod
    def from_fixture(cls, name):
        return cls.from_file(fixture(name))


def build_mock(name):
    collection = PostmanCollectionV21.from_fixture(name)
    mock = requests_mock(
        collection,
        assert_all_requests_are_fired=False
    )
    return mock


class TestCaseInsensitiveDict(unittest.TestCase):

    def test_init1(self):
        idict = CaseInsensitivesDict([('Content-Type', 'application/json')])
        self.assertEqual(len(idict), 1)
        self.assertIn('content-type', idict)

    def test_init2(self):
        idict = CaseInsensitivesDict(**{'Content-Type': 'application/json'})
        self.assertEqual(len(idict), 1)
        self.assertIn('content-type', idict)

    def test_del(self):
        idict = CaseInsensitivesDict([('Content-Type', 'application/json')])
        self.assertEqual(len(idict), 1)
        del idict['content-type']
        self.assertEqual(len(idict), 0)

    def test_iter(self):
        idict = CaseInsensitivesDict([('Content-Type', 'application/json')])
        self.assertEqual(list(idict), ['content-type'])


class TestRequestMatching(unittest.TestCase):

    def test_validate(self):
        self.assertRaises(ValidationError, PostmanCollectionV21, {})

    def test_basic_request(self):
        with build_mock('basic.json'):
            resp = requests.get('http://httpbin.org/ip')
            self.assertEqual(resp.json(), {'origin': '1.1.1.1'})

    def test_invalid_method(self):
        '''
        The request expects a GET but we perform a POST.
        '''

        with build_mock('basic.json'):
            with self.assertRaises(ConnectionError):
                requests.post('http://httpbin.org/ip')

    def test_invalid_url(self):
        '''
        The URL is unknown by the request.
        '''

        with build_mock('basic.json'):
            with self.assertRaises(ConnectionError):
                requests.get('http://httpbin.org/status/404')

    def test_folders_support(self):
        '''
        Folder and sub-folders are supported. folders.json contains the
        following structure:

                folde (an item)
                 |-> subfolder (an item)
                      |-> test (request)
        '''

        with build_mock('folders.json'):
            resp = requests.get('http://httpbin.org/ip')
            self.assertEqual(resp.json(), {'origin': '1.1.1.1'})

    def test_missing_header(self):
        '''
        The original request requires an header that is not explicited.
        '''

        with build_mock('header.json'):
            with self.assertRaises(ConnectionError):
                requests.get('http://httpbin.org/headers')

    @unittest.expectedFailure
    def test_body_missing(self):
        '''
        body.formdata.json has a request with some data, but this use
        case is not support yet.
        '''

        with build_mock('body.formdata.json'):
            with self.assertRaises(ConnectionError):
                requests.post('http://httpbin.org/anything')

    def test_basic_auth_missing(self):
        '''
        Because we didn't specify any authentication method and the
        request explicitely requires basic auth, raise ConnectionError.
        If you need to return 401, create a new request with no auth.
        '''

        with build_mock('basic_auth.json'):
            with self.assertRaises(ConnectionError):
                requests.get('http://httpbin.org/basic-auth/me/pwd')

    def test_basic_auth_401(self):
        '''
        We explicitely created a request with wrong credentials that
        returns 401.
        '''

        with build_mock('basic_auth.json'):
            response = requests.get(
                'http://httpbin.org/basic-auth/me/pwd',
                auth=('me', 'wrong-pwd')
            )
            self.assertEqual(response.status_code, 401)

    def test_basic_auth_200(self):
        '''
        Test a request with the right credentials.
        '''

        with build_mock('basic_auth.json'):
            response = requests.get(
                'http://httpbin.org/basic-auth/me/pwd',
                auth=('me', 'pwd')
            )
        self.assertEqual(response.status_code, 200)


class TestResponses(unittest.TestCase):

    def test_status_code(self):
        with build_mock('statuscode.json'):
            resp = requests.get('http://httpbin.org/status/404')
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(resp.text, '')

    def test_headers(self):
        with build_mock('header.json'):
            headers = {'X-Key': 'value'}
            resp = requests.get('http://httpbin.org/headers', headers=headers)
            self.assertEqual(resp.status_code, 200)

    def test_body_form_data(self):
        with build_mock('body.formdata.json'):
            data = {'key': 'value'}
            resp = requests.post('http://httpbin.org/anything', data=data)
            self.assertEqual(resp.json()['form'], data)

class TestMiscellanea(unittest.TestCase):

    def test_string_request(self):
        '''
        The specifications says that requests could be string.
        Interpret them as simply GETs with no headers.
        '''

        with build_mock('string_request.json'):
            resp = requests.get('http://httpbin.org/ip')
            self.assertEqual(resp.json(), {'origin': '1.1.1.1'})
