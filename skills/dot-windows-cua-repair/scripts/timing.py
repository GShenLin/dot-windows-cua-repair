"""Preview optional timing instrumentation; rollback with the generated manifest."""
import argparse
import json
from pathlib import Path
from repair import BASELINES
from repair_files import digest, transaction

PREFIX = '''import {appendFileSync as cuaTimingAppend} from"node:fs";
import {cwd as cuaTimingCwd} from"node:process";
import {join as cuaTimingJoin} from"node:path";
function cuaTiming(stage,type){try{cuaTimingAppend(cuaTimingJoin(cuaTimingCwd(),"cua-browser-timing.log"),JSON.stringify({time:new Date().toISOString(),stage,type})+"\\n")}catch{console.error("CUA timing log write failed")}}
'''
REPLACEMENTS = {
    'async runCommand(e,r){return await this.ensureCommandAllowed(e),await r()}':
    'async runCommand(e,r){cuaTiming("security:start",e.type);await this.ensureCommandAllowed(e);cuaTiming("security:done",e.type);try{return await r()}finally{cuaTiming("operation:done",e.type)}}',
    'return await t.fetch(e,r)}var wz=':
    'cuaTiming("site-status:start","fetch");try{return await t.fetch(e,r)}finally{cuaTiming("site-status:done","fetch")}}var wz=',
}


def instrument(data):
    if digest(data) != BASELINES['browser_service_sha256']:
        raise ValueError('Unrecognized/modified browser service; no instrumentation applied')
    text = data.decode('utf-8')
    for before, after in REPLACEMENTS.items():
        if text.count(before) != 1:
            raise ValueError('Timing anchor mismatch')
        text = text.replace(before, after)
    return (PREFIX + text).encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', required=True)
    parser.add_argument('--backup-dir')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = Path(args.service).absolute()
    before = path.read_bytes()
    after = instrument(before)
    result = {'apply': args.apply, 'target': str(path), 'original_sha256': digest(before),
              'instrumented_sha256': digest(after), 'log': '<task cwd>/cua-browser-timing.log'}
    if args.apply:
        if not args.backup_dir:
            parser.error('--backup-dir is required with --apply')
        result['manifest'] = str(transaction([(path, before, after)], args.backup_dir, 'Temporary CUA timing'))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
