import json
from os.path import dirname, join as joinpath
import time
import unittest
from postman_requests_mock import (
    PostmanCollectionV21 as _PostmanCollectionV21, ValidationError,
    CaseInsensitivesDict, requests_mock, PostmanFormatter, load_scope_from_file
)
import requests
from requests.exceptions import ConnectionError


def fixture(name):
    return joinpath(dirname(__file__), name)


def load_scope(name):
    return load_scope_from_file(fixture(name))


class PostmanCollectionV21(_PostmanCollectionV21):

    # load the cached version of the schema to speed up the tests and
    # avoid network communication
    with open(fixture('collection.json'), encoding='utf8') as fp:
        _schema = json.load(fp)

    @classmethod
    def from_fixture(cls, name, global_scope={}, environment={}):
        return cls.from_file(fixture(name), global_scope, environment)


def build_mock(name, global_scope={}, env={}):
    collection = PostmanCollectionV21.from_fixture(name, global_scope, env)
    mock = requests_mock(collection, assert_all_requests_are_fired=False)
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

    def test_repr(self):
        idict = CaseInsensitivesDict([('Content-Type', 'application/json')])
        self.assertEqual(repr(idict), "{'content-type': 'application/json'}")


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

    def test_params(self):
        '''
        The mock recognizes parametrized urls and substitures the
        parameters with the given values.
        '''

        with build_mock('param.json'):
            response = requests.get('http://httpbin.org/anything/test')
        self.assertEqual(response.status_code, 200)

    def test_invalid_params(self):
        '''
        The parameter must match the given value or it will not match.
        '''

        with build_mock('param.json'):
            with self.assertRaises(ConnectionError):
                requests.get('http://httpbin.org/anything/try')

    def test_string_url(self):
        '''
        Test the case the request url is a string.
        '''

        with build_mock('string_url.json'):
            response = requests.get('http://httpbin.org/ip')
        self.assertEqual(response.status_code, 200)

    def test_no_scheme(self):
        '''
        By default the scheme is http.
        '''

        with build_mock('no_scheme.json'):
            response = requests.get('http://httpbin.org/ip')
        self.assertEqual(response.status_code, 200)

    def test_port(self):
        '''
        Test a request to a non standard port.
        '''

        with build_mock('port.json'):
            response = requests.get('http://httpbin.org:8080/ip')
        self.assertEqual(response.status_code, 200)

    def test_no_path(self):
        '''
        Test when the path is missing.
        '''

        with build_mock('no_path.json'):
            response = requests.get('http://httpbin.org/')
        self.assertEqual(response.status_code, 200)

    def test_fragment(self):
        '''
        Test a request with a fragment.
        '''

        with build_mock('fragment.json'):
            response = requests.get('http://httpbin.org/ip#fragment')
        self.assertEqual(response.status_code, 200)

    def test_collection_variables(self):
        '''
        Variables in the URL and URL parameters are correctly expanded.
        '''

        data = {'myparam': 'value'}
        with build_mock('var_expansion.json'):
            resp = requests.get('http://httpbin.org:80/anything', data=data)
            self.assertEqual(resp.status_code, 200)

    def test_header_variable(self):
        '''
        Variables in the headers are correctly expanded too.
        '''

        headers = {'myparam': 'value'}
        with build_mock('var_expansion.json'):
            resp = requests.get('http://httpbin.org/headers', headers=headers)
            self.assertEqual(resp.status_code, 200)

    def test_global_scope(self):
        '''
        Use the global scope to expand the variables.
        '''

        globals = {'host': 'httpbin.org'}
        with build_mock('var_expansion2.json', globals):
            resp = requests.get('http://httpbin.org/get')
            self.assertEqual(resp.status_code, 200)

    def test_environment(self):
        '''
        The environment scope take precedence over the global scope.
        '''

        globals = {'host': 'example.com'}
        env = {'host': 'httpbin.org'}
        with build_mock('var_expansion2.json', globals, env):
            resp = requests.get('http://httpbin.org/get')
            self.assertEqual(resp.status_code, 200)



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

    def test_load_scope(self):
        self.assertEqual(load_scope('globals.json'), {'host': 'httpbin.org'})

    def test_load_scope_var_disabled(self):
        '''
        environment.json define one variable but it is disabled and ence do not
        load it.
        '''

        self.assertEqual(load_scope('environment.json'), {})


class TestFormatter(unittest.TestCase):

    def test_formatter(self):
        s = 'hello {{who}}'
        formatter = PostmanFormatter()
        expected = formatter.format(s, who='world')
        self.assertEqual(expected, 'hello world')

    def test_trim_spaces(self):
        s = 'hello {{ who }}'
        formatter = PostmanFormatter()
        expected = formatter.format(s, who='world')
        self.assertEqual(expected, 'hello world')

    def test_no_variables(self):
        s = 'hello world'
        formatter = PostmanFormatter()
        expected = formatter.format(s, who='world')
        self.assertEqual(expected, 'hello world')

    def test_dynamic_variables(self):
        formatter = PostmanFormatter()
        s = '{{$guid}}'
        self.assertRegex(
            formatter.format(s),
            r'[0-9a-h]{8}-([0-9a-h]{4}-){3}[0-9a-h]{12}'
        )
        s = '{{$timestamp}}'
        t0 = time.time()
        expected = formatter.format(s)
        t1 = time.time()
        self.assertTrue(t0 <= float(expected) <= t1)
        self.assertTrue(0 <= int(formatter.format('{{$randomInt}}')) <= 1000)

    def test_field_not_found(self):
        s = 'hello {{who}}'
        self.assertEqual(PostmanFormatter().format(s), s)
