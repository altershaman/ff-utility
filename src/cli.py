import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog='ff',
        description='Fractality Framework v0.0.1',
    )
    subparsers = parser.add_subparsers(dest='command')
    subparsers.add_parser('init', help='Initialize a Bounded Belief store')

    args = parser.parse_args()

    if args.command == 'init':
        from src.commands.init import cmd_init
        cmd_init()
    else:
        print("Fractality Framework v0.0.1")
        print("Try ff -h to get help on commands")
