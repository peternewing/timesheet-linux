#!/usr/bin/python3
"""Offline smoke test of bundled Jev/TLS/key-storage dependencies.

Creates no database, keyring item, or network request.
"""
import ssl

import gi
gi.require_version('Secret','1')
from gi.repository import Secret
from timesheet import jev

schema=Secret.Schema.new('org.local.TimeSheetLinux.RuntimeCheck',Secret.SchemaFlags.NONE,{'scope':Secret.SchemaAttributeType.STRING})
assert schema is not None
assert jev.ENDPOINT=='https://api.typesafe.ai/v1/systemone'
context=ssl.create_default_context()
assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
assert context.cert_store_stats()['x509_ca']>0, 'No system TLS trust roots were found'
print('PASS: bundled TypeSafe client, TLS trust and libsecret import/schema')
