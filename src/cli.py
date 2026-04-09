import argparse
import sys


def main():
    if len(sys.argv) < 2:
        print('Fractality Framework v0.0.1')
        print('Try ff -h to get help on commands')
        return

    if sys.argv[1] == 'init':
        from src.commands.init import cmd_init
        cmd_init()
        return

    parser = argparse.ArgumentParser(
        prog='ff',
        description='Fractality Framework v0.0.1',
    )
    parser.add_argument('content', nargs='?', metavar='content',
                        help='File path or string. Prefix with ? to suggest (e.g. ff ?"<query>")')
    parser.add_argument('--genesis', action='store_true',
                        help='Record content as a new concept')
    parser.add_argument('--branch', metavar='uuid|alias',
                        help='With --genesis: declare provenance (source concept)')
    parser.add_argument('--merge', metavar='uuid|alias',
                        help='Absorb a concept into the target --uuid concept')
    parser.add_argument('-id', '--uuid', metavar='uuid',
                        help='Target concept by full UUID or prefix')
    parser.add_argument('-a', '--alias', nargs='+', metavar='alias',
                        help='Target concept by alias, or reassign: --alias <current> <new>')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    parser.add_argument('--markdown', action='store_true',
                        help='Write concept content as MD files to working tree')
    parser.add_argument('--full', action='store_true',
                        help='Return full content instead of excerpt')

    args = parser.parse_args()

    # Detect and strip '?' prefix — marks suggest mode explicitly
    if args.content and args.content.startswith('?'):
        args.content = args.content[1:]
        args._suggest = True
    else:
        args._suggest = False

    from src.commands.concept import cmd_concept
    cmd_concept(args)
