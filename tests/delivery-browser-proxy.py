#!/usr/bin/env python3
"""Synthetic HTTPS reverse proxy for the disposable browser fixture only."""

import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import ssl


def main():
    run = os.environ.get('SQMAIL_MAIL_TEST_RUN', '')
    if (not Path('/.dockerenv').exists()
            or os.environ.get('SQMAIL_DISPOSABLE_TEST') != '1'
            or not re.fullmatch('[a-f0-9]{32}', run)
            or Path('/tmp/sqmail-mail-test-run').read_text().strip() != run):
        raise RuntimeError('Use only the disposable MailEnvironment fixture')

    # These credentials exist only in this fresh, internally networked fixture.
    password = 'SyntheticAdminOnly927'
    credentials = Path('/var/qmail/control/lighttpd-admins.htdigest')
    credentials.write_text(''.join(
        user + ':SQMail AIO Admin:'
        + hashlib.sha256(f'{user}:SQMail AIO Admin:{password}'.encode()).hexdigest() + '\n'
        for user in ('admin', 'operator')))
    credentials.chmod(0o644)

    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 300000:
                self.send_error(413)
                return
            body = self.rfile.read(length) if length else None
            headers = {name: value for name, value in self.headers.items()
                       if name.lower() not in ('connection', 'transfer-encoding')}
            headers['X-Forwarded-Proto'] = 'https'
            upstream = http.client.HTTPConnection('127.0.0.1', 88, timeout=90)
            try:
                upstream.request(self.command, self.path, body, headers)
                response = upstream.getresponse()
                data = response.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise RuntimeError('Oversized response from test application')
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in ('connection', 'transfer-encoding', 'content-length'):
                        self.send_header(name, value)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            finally:
                upstream.close()

    server = ThreadingHTTPServer(('0.0.0.0', 9443), Proxy)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('/ssl/http.crt', '/ssl/http.key')
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print('READY synthetic HTTPS proxy', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
