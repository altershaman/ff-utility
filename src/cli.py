import argparse
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '-c':
        sys.argv[1] = 'concept'

    parser = argparse.ArgumentParser(
        prog='ff',
        description='Fractality Framework v0.0.1',
    )
    subparsers = parser.add_subparsers(dest='command')
    subparsers.add_parser('init', help='Initialize a Bounded Belief store')

    concept_p = subparsers.add_parser('concept', help='Work with concepts')
    concept_p.add_argument('concept', nargs='?', metavar='content',
                           help='File path or string')
    concept_p.add_argument('--genesis', action='store_true',
                           help='Record content as a new genesis concept')
    concept_p.add_argument('-id', '--uuid', metavar='uuid',
                           help='Target concept by full UUID or prefix')
    concept_p.add_argument('-a', '--alias', metavar='alias',
                           help='Target concept by alias from last output')
    concept_p.add_argument('--json', action='store_true',
                           help='Output as JSON')
    concept_p.add_argument('--md', action='store_true',
                           help='Write concept content as MD files')
    concept_p.add_argument('--full', action='store_true',
                           help='Return full content instead of excerpt')

    args = parser.parse_args()

    if args.command == 'init':
        from src.commands.init import cmd_init
        cmd_init()
    elif args.command == 'concept':
        from src.commands.concept import cmd_concept
        cmd_concept(args)
    else:
        print('Fractality Framework v0.0.1')
        print('Try ff -h to get help on commands')
