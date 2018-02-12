#!/usr/bin/python
#
# Copyright 2017 Ben Walsh
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
import logging
import datetime
import json
import subprocess
import shutil
import getpass

logging.basicConfig(level=logging.DEBUG)

import argparse

_logger = logging.getLogger(__name__)


def _write_env(fname):
    with open(fname, 'wb') as fp:
        for k, v in os.environ.items():
            fp.write('%s=%s\n' % (k, v))


def _read_conf():
    res = {}
    fname = os.path.expanduser('~/.cronrun')
    with open(fname) as fp:
        res = dict([line.strip().split('=') for line in fp])
    return res


def _read_json(fname):
    if not os.path.exists(fname):
        return {}
    with open(fname, 'rb') as fp:
        data = fp.read()
        if '{' not in data:
            return {}
        return json.loads(data)


def _write_json(fname, obj):
    with open(fname + '.new', 'wb') as fp:
        fp.write('%s\n' % json.dumps(obj))

    os.rename(fname + '.new', fname)


def _send_mail(conf, args, status_str, log_prefix):
    from_address = '%s@localhost' % getpass.getuser()
    subject = '%s: %s' % (status_str, args.name)

    if args.test:
        _logger.info('Sending mail "%s".', status_str)
        _logger.info('conf = %r', conf)
        mailx_cmd = ['cat']
    else:
        mailx_cmd = [conf['CRONRUN_MAILX'], '-s', subject,
                     '-r', from_address, conf['CRONRUN_MAILEE']]

    proc = subprocess.Popen(['tail', '-50', log_prefix + '.log'], stdout=subprocess.PIPE)
    proc2 = subprocess.Popen(mailx_cmd, stdin=proc.stdout)
    proc.wait()
    proc2.wait()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--test', default=False, action='store_true')
    parser.add_argument('--report-always', default=False, action='store_true')
    parser.add_argument('--report-after', type=int, default=1,
                        help='Report when this many failures reached')
    parser.add_argument('--report-all-after', type=int, default=None,
                        help='Report every failure after this point')
    parser.add_argument('name')
    parser.add_argument('cmd', nargs=argparse.REMAINDER)

    args = parser.parse_args()

    conf = _read_conf()

    date_str = datetime.datetime.now().strftime('%Y%m%d%H%M%S')

    log_dirname = os.path.expanduser('~/log')

    log_prefix = os.path.join(log_dirname, '%s.%s' % (args.name, date_str))
    stat_fname = os.path.join(log_dirname, '%s.status' % (args.name))

    _write_env(log_prefix + '.env')
    status = _read_json(stat_fname)

    tmp_fname = '/tmp/cronrun.%s' % (os.getpid())

    null_fd = open('/dev/null', 'rb')

    with open(tmp_fname + '.log', 'wb') as log_fd:
        proc = subprocess.Popen(args.cmd, stdin=null_fd,
                                stdout=log_fd, stderr=subprocess.STDOUT,
                                close_fds=True, cwd='/')
        proc.wait()
        rc = proc.returncode

    shutil.move(tmp_fname + '.log', log_prefix + '.log')

    nfails = status.get('nfails', None)
    if rc == 0:
        if args.report_always or nfails != 0:
            _send_mail(conf, args, 'Success', log_prefix)
            status['nfails'] = 0
    else:
        nfails = 1 if nfails is None else nfails + 1
        if (args.report_always
                or args.report_after is not None and nfails == args.report_after
                or args.report_all_after is not None and nfails >= args.report_all_after):
            _send_mail(conf, args, 'FAILURE', log_prefix)
            status['nfails'] = nfails

    _write_json(stat_fname, status)

    return 0


if __name__ == '__main__':
    sys.exit(main())
