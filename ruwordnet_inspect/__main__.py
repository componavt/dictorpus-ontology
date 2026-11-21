"""Command line entry point.

Usage:
    python3 -m ruwordnet_inspect build \
        --ruwordnet-dir /path/to/ruwordnet --out ruwordnet.work
"""
import argparse
import json
import sys

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='ruwordnet_inspect',
        description='Local RuWordNet domain schema browser (read-only).')
    parser.add_argument('--version', action='version',
                        version='ruwordnet_inspect ' + __version__)
    sub = parser.add_subparsers(dest='command', required=True)

    p_build = sub.add_parser(
        'build', help='parse XML and produce all outputs in --out')
    p_build.add_argument('--ruwordnet-dir', required=True,
                         help='directory with RuWordNet XML files')
    p_build.add_argument('--out', required=True,
                         help='output directory (e.g. ruwordnet.work)')

    args = parser.parse_args(argv)
    if args.command == 'build':
        from .build import build
        summary = build(args.ruwordnet_dir, args.out)
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=1)
        sys.stdout.write('\n')
        ok = (summary['checks']['input_files_unchanged'] is not False
              and not summary['checks']['witness_errors'])
        return 0 if ok else 1
    parser.error('unknown command %r' % args.command)


if __name__ == '__main__':
    sys.exit(main())
