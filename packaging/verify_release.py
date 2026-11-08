#!/usr/bin/python3
"""Verify a release binary using GitHub's cryptographic provenance verifier."""
import argparse
import shutil
import subprocess
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('artifact',type=Path);parser.add_argument('--bundle',type=Path)
parser.add_argument('--source-commit',help='Expected full source commit SHA from the release')
args=parser.parse_args()
if not args.artifact.is_file():parser.error('The downloaded artifact does not exist.')
gh=shutil.which('gh')
if not gh:parser.error('Install GitHub CLI from your distribution or https://cli.github.com before verifying provenance.')
command=[gh,'attestation','verify',str(args.artifact.resolve()),'--repo','peternewing/timesheet-linux',
    '--signer-workflow','peternewing/timesheet-linux/.github/workflows/packages.yml',
    '--source-ref','refs/heads/main','--deny-self-hosted-runners']
if args.bundle:command+=['--bundle',str(args.bundle.resolve())]
if args.source_commit:
    import re
    if not re.fullmatch('[0-9a-f]{40}',args.source_commit):parser.error('Use a full 40-character source commit SHA.')
    command+=['--source-digest',args.source_commit]
raise SystemExit(subprocess.run(command,check=False).returncode)
