# Copyright (c) 2018 Marco Giusti

from os.path import join as joinpath, dirname, abspath
from setuptools import setup


SETUPDIR = abspath(dirname(__file__))


def version():
    glb = {}
    with open(joinpath(SETUPDIR, 'src', 'postman_requests_mock.py')) as fp:
        for line in fp:
            if '__version__' in line:
                exec(line, glb)
                return glb['__version__']
    raise RuntimeError('__version__ not found')


def long_description():
    with open(joinpath(SETUPDIR, 'README')) as fp:
        return fp.read()


setup(
    name='postman_requests_mock',
    version=version(),
    description=(
        'Library that uses Postman collections to mock the requests library'
    ),
    long_description=long_description(),
    author='Marco Giusti',
    author_email='marco.giusti@posteo.de',
    license='MIT',
    url='https://github.com/marcogiusti/postman_requests_mock',
    py_modules=['postman_requests_mock'],
    package_dir={'': 'src'},
    install_requires=[
        'jsonschema',
        'requests',
        'responses'
    ],
    extras_require={
        'dev': [
            'pycodestyle',
            'pyflakes',
            'tox'
        ]
    },
    classifiers=(
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    )
)
