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

from timesheet import automation_worker, automation_store, decision_context, evaluate, updates
from timesheet.decision_policy import settings
assert settings('{}')['mode']=='off'
assert callable(automation_worker.Engine.step) and callable(automation_store.Repository.complete)
print('PASS: bundled automation policy, worker, queue, evaluation and update modules; default off')

from timesheet import simple_ui, simple_setup, simple_store, day_record
assert len(simple_setup.BUCKETS)==4 and callable(day_record.pdf)
print('PASS: bundled simple setup, daily record and category controls')

record=dict(day='2026-11-08',generated=0,active=0,away=0,gaps=0,ai=0,human=0,unclassified=0,categories=[],entries=[],activity=[])
assert day_record.pdf(record).startswith(b'%PDF')
print('PASS: bundled simple day-record PDF generation')

from timesheet import daily_choices
assert callable(daily_choices.apply_saved)
print('PASS: bundled local daily-choice continuation')

from timesheet import day_organiser
assert callable(day_organiser.request) and callable(day_organiser.ready_to_work)
print('PASS: bundled one-click day organiser')
