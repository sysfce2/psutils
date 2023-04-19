import pkg_resources

VERSION = pkg_resources.require('psutils')[0].version
version_banner=f'''\
%(prog)s {VERSION}
Copyright (c) Reuben Thomas 2023.
Released under the GPL version 3, or (at your option) any later version.
'''

import argparse
import os
import re
import sys
import warnings
from typing import Dict, List, Optional

from psutils import (
    HelpFormatter, die, extn, filename, setup_input_and_output,
    simple_warning,
)

def get_parser() -> argparse.ArgumentParser:
    # Command-line arguments
    parser = argparse.ArgumentParser(
        description='Extract resources from a PostScript document.',
        formatter_class=HelpFormatter,
        usage='%(prog)s [OPTION...] [INFILE [OUTFILE]]',
        add_help=False,
    )
    warnings.showwarning = simple_warning(parser.prog)

    parser.add_argument('-m', '--merge', action='store_true',
                        help='''merge resources of the same name into one file
(needed e.g. for fonts output in multiple blocks)''')
    parser.add_argument('--help', action='help',
                        help='show this help message and exit')
    parser.add_argument('-v', '--version', action='version',
                        version=version_banner)
    parser.add_argument('infile', metavar='INFILE', nargs='?',
                        help="`-' or no INFILE argument means standard input")
    parser.add_argument('outfile', metavar='OUTFILE', nargs='?',
                        help="`-' or no OUTFILE argument means standard output")
    return parser

def main(argv: List[str]=sys.argv[1:]) -> None: # pylint: disable=dangerous-default-value
    args = get_parser().parse_intermixed_args(argv)

    infile, outfile = setup_input_and_output(args.infile, args.outfile)

    # Resource types
    def get_type(comment: str) -> Optional[str]:
        types = {'%%BeginFile:': 'file', '%%BeginProcSet:': 'procset',
                '%%BeginFont:': 'font'}
        return types.get(comment, None)

    # Extract resources
    resources: Dict[str, List[str]] = {} # resources included
    merge: Dict[str, bool] = {} # resources extracted this time
    prolog: List[str] = []
    body: List[str] = []
    output: Optional[List[str]] = prolog

    for line in infile:
        if re.match(r'%%Begin(Resource|Font|ProcSet):', line):
            comment, *res = line.split() # look at resource type
            resource_type = get_type(comment) or res.pop(0)
            name = filename(*res, extn(resource_type)) # make file name
            saveout = output
            if resources.get(name) is None:
                prolog.append(f'%%IncludeResource: {resource_type} {" ".join(res)}\n')
                if not os.path.exists(name):
                    try:
                        fh = open(name, 'w')
                    except IOError:
                        die("can't write file `$name'", 2)
                    resources[name] = []
                    merge[name] = args.merge
                    output = resources[name]
                else: # resource already exists
                    if fh is not None:
                        fh.close()
                    output = None
            elif merge.get(name):
                try:
                    fh = open(name, 'a+')
                except IOError:
                    die("can't append to file `$name'", 2)
                resources[name] = []
                output = resources[name]
            else: # resource already included
                output = None
        elif re.match(r'%%End(Resource|Font|ProcSet)', line):
            if output is not None:
                output.append(line)
                fh.writelines(output)
            output = saveout
            continue
        elif re.match(r'%%End(Prolog|Setup)', line) or line.startswith('%%Page:'):
            output = body
        if output is not None:
            output.append(line)

    outfile.writelines(prolog)
    outfile.writelines(body)


if __name__ == '__main__':
    main()