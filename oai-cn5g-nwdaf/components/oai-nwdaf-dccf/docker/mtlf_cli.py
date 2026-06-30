#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_DB = os.environ.get('DCCF_DB_PATH','/data/casmella.db')

parser = argparse.ArgumentParser(prog='mtlf')
subparsers = parser.add_subparsers(dest='cmd')

subparsers.add_parser('status')
proc = subparsers.add_parser('process')
proc.add_argument('--input', default='/workspace/raw')
proc.add_argument('--output', default='/workspace/dataset.pt')

args = parser.parse_args()

if args.cmd == 'status':
    print('MTLF status')
    print('  DCCF DB:', DEFAULT_DB, 'exists=' , Path(DEFAULT_DB).exists())
    print('  /workspace exists=', Path('/workspace').exists())
    print('  /models exists=', Path('/models').exists())
    sys.exit(0)

if args.cmd == 'process':
    script = Path('/app/process_data_serial_chain.py')
    if not script.exists():
        print('process_data_serial_chain.py not found at /app/', file=sys.stderr)
        sys.exit(1)
    cmd = [sys.executable, str(script), '--input', args.input, '--output', args.output]
    print('Running:', ' '.join(cmd))
    rc = subprocess.call(cmd)
    sys.exit(rc)

parser.print_help()
