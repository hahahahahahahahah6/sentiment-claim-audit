import argparse
import json
import sys
from . import __version__
from .core import audit


def main(argv=None):
    parser = argparse.ArgumentParser(description='Audit documented claims against Python source evidence.')
    parser.add_argument('root')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[] , metavar='PATH_PREFIX')
    parser.add_argument('--fail-on', choices=['LOW', 'MEDIUM', 'HIGH'], default='HIGH')
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 1
    try:
        result = audit(args.root, args.ignore)
    except (OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result['status'])
        for f in result['findings']:
            print('{severity} {rule_id}: {message}'.format(**f))
        if args.verbose:
            print('Production evidence: ' + ', '.join(result['evidence']['production']))
            print('Test evidence: ' + ', '.join(result['evidence']['tests']))
    ranks = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
    return 2 if any(ranks[f['severity']] >= ranks[args.fail_on] for f in result['findings']) else 0


if __name__ == '__main__':
    sys.exit(main())
