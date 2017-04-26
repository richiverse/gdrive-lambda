#! /usr/bin/env python2
from os import environ as env
from functools import partial
import random
import string
import urllib

try:
    from jose import jwt
except ImportError:
    pass

from flask import url_for

try:
    encrypt = partial(jwt.encode, key=env['APP_SECRET'], algorithm='HS256')
    decrypt = partial(jwt.decode, key=env['APP_SECRET'], algorithms=['HS256'])
except NameError:
    pass


def list_routes(app):
    output = []
    for rule in app.url_map.iter_rules():

        if rule.endpoint == 'static':
            continue

        options = {}
        for arg in rule.arguments:
            options[arg] = "[{0}]".format(arg)

        methods = ','.join(
            rule for rule in rule.methods
            if rule not in ('OPTIONS', 'HEAD'))
        url = url_for(rule.endpoint, **options)
        line = urllib.unquote(
            "{:7s}{:30s}{}".format(methods, url, rule.endpoint))
        output.append(line)

    return [ln for ln in sorted(output)]


def random_string(size=64):
    return ''.join(
        random.SystemRandom().choice(
            string.ascii_letters + string.digits)
        for _ in range(size)
    )


if __name__ == '__main__':
    print(random_string())
