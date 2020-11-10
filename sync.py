# Foxpass to Duo user sync script
#
# Copyright (c) 2017-present, Foxpass, Inc.
# All rights reserved.
#
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


import argparse
import logging
import requests
from six.moves.urllib import parse
import sys
import time
import os

import duo_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description='Sync between Foxpass and Duo.')
parser.add_argument('--once', action='store_true', help='Run once and exit (or non-empty FOXPASS_DUO_SYNC_ONCE env. var.)')
parser.add_argument('--interval', default=5, type=int, help='Minutes to wait between runs')
parser.add_argument('--foxpass-hostname', default='https://api.foxpass.com',
                    help='Foxpass API URL, e.g. https://api.foxpass.com (or FOXPASS_HOSTNAME env. var.)')
parser.add_argument('--foxpass-api-key', help='Foxpass API key (or FOXPASS_API_KEY env. var.)')
parser.add_argument('--foxpass-group', help='Foxpass group name to sync (or FOXPASS_GROUP env. var.)')
parser.add_argument('--duo-hostname', help='Duo URL, e.g. duo-XXXX.duosecurity.com (or DUO_HOSTNAME env. var.)')
parser.add_argument('--duo-ikey', help='Duo API ikey (or DUO_IKEY env. var.)')
parser.add_argument('--duo-skey', help='Duo API skey (or DUO_SKEY env. var.)')
ARGS = parser.parse_args()

try:
    FOXPASS_HOSTNAME = ARGS.foxpass_hostname or os.environ['FOXPASS_HOSTNAME']
    FOXPASS_API_KEY = ARGS.foxpass_api_key or os.environ['FOXPASS_API_KEY']

    DUO_HOSTNAME = ARGS.duo_hostname or os.environ['DUO_HOSTNAME']
    DUO_IKEY = ARGS.duo_ikey or os.environ['DUO_IKEY']
    DUO_SKEY = ARGS.duo_skey or os.environ['DUO_SKEY']
except KeyError as e:
    logger.error('No value in args. or env. for {}'.format(str(e)))
    sys.exit(1)

FOXPASS_GROUP = ARGS.foxpass_group or os.environ.get('FOXPASS_GROUP', None)
FOXPASS_DUO_SYNC_ONCE = bool(ARGS.once or os.environ.get('FOXPASS_DUO_SYNC_ONCE', None))

FOXPASS_REQUEST_HEADERS={'Accept': 'application/json',
                         'Authorization': 'Token {}'.format(FOXPASS_API_KEY)}

admin_api = duo_client.Admin(
    ikey=DUO_IKEY,
    skey=DUO_SKEY,
    host=DUO_HOSTNAME
)

def get_foxpass_users_in_group(group):
    group_url = parse.urljoin(FOXPASS_HOSTNAME, '/v1/groups/{}/members/'.format(group))

    r = requests.get(group_url, headers=FOXPASS_REQUEST_HEADERS)
    r.raise_for_status()

    json_data = r.json()

    if 'data' in json_data:
        return [user['username'] for user in json_data['data']]

    return None

def get_all_foxpass_users():
    url = parse.urljoin(FOXPASS_HOSTNAME, '/v1/users/')

    r = requests.get(url, headers=FOXPASS_REQUEST_HEADERS)
    r.raise_for_status()
    json_data = r.json()

    if 'data' in json_data:
        return json_data['data']

    return None

def sync():
    duo_users_by_email = {}
    for user in admin_api.get_users():
        if user['email']:
            duo_users_by_email[user['email']] = user

    foxpass_users = get_all_foxpass_users()

    group_members = None
    if FOXPASS_GROUP:
        group_members = set(get_foxpass_users_in_group(FOXPASS_GROUP))

    # make a set of foxpass users that should be in duo. they must be active and if a group is
    # specified, they must be in that group
    foxpass_users_by_email = {}
    for user in foxpass_users:
        if user['active'] and (not group_members or user['username'] in group_members):
            foxpass_users_by_email[user['email']] = user

    # - duo_users_by_email is all duo users by email addresses
    # - foxpass_users_by_email is all foxpass user by
    #   email addresses for ACTIVE foxpass users

    # enroll into duo every foxpass email address that's not already there
    for email, fp_user in foxpass_users_by_email.items():
         # already in duo? skip to next
         if email in duo_users_by_email:
             continue

         logger.info("Need to enroll {}".format(email))
         try:
             admin_api.enroll_user(fp_user['username'], email)
         except:
             logger.exception("Can't enroll user {}".format(email))

def main():
    while True:
        try:
            sync()
        except KeyboardInterrupt:
            return
        except:
            logger.exception('Unhandled exception during sync')

        if FOXPASS_DUO_SYNC_ONCE:
            return

        logger.info('Sleeping for {} minuntes'.format(ARGS.interval))
        time.sleep(ARGS.interval * 60) # interval is in minutes. Covert to seconds.

if __name__ == '__main__':
    main()
