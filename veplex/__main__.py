"""Command line entry point.

Usage:
    python3 -m veplex inventory --data veplex.work/data --out veplex.work
    python3 -m veplex sample --out veplex.work [--per-lang 60 ...]
"""
import argparse
import json
import sys

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='veplex',
        description='VepKar dictionary sememe inventory (stage A).')
    parser.add_argument('--version', action='version',
                        version='veplex ' + __version__)
    sub = parser.add_subparsers(dest='command', required=True)

    p_inv = sub.add_parser('inventory', help='build the sememe registry')
    p_inv.add_argument('--data', required=True,
                       help='dictorpus-data snapshot directory (at a tag)')
    p_inv.add_argument('--out', required=True, help='output directory')

    p_sample = sub.add_parser('sample', help='B1 review sample')
    p_sample.add_argument('--out', required=True,
                          help='directory with sememes.tsv')
    p_sample.add_argument('--per-lang', type=int, default=60)
    p_sample.add_argument('--short', type=int, default=25)
    p_sample.add_argument('--long', type=int, default=25)
    p_sample.add_argument('--seed', type=int, default=42)

    args = parser.parse_args(argv)
    if args.command == 'inventory':
        from .outputs import run_inventory
        totals = run_inventory(args.data, args.out)
        json.dump(totals, sys.stdout, ensure_ascii=False, indent=1)
        sys.stdout.write('\n')
        return 0
    if args.command == 'sample':
        from .sample import build_sample, write_sample
        rows = build_sample(args.out, per_lang=args.per_lang,
                            n_short=args.short, n_long=args.long,
                            seed=args.seed)
        path = write_sample(args.out, rows)
        print('sample rows: %d -> %s' % (len(rows), path))
        return 0
    parser.error('unknown command %r' % args.command)


if __name__ == '__main__':
    sys.exit(main())
