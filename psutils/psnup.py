import importlib.metadata
import argparse
import re
import sys
import warnings
from typing import Any, List, Optional, Sequence, Tuple, Union

from psutils import (
    HelpFormatter,
    add_basic_arguments,
    add_paper_arguments,
    die,
    Rectangle,
    document_transform,
    get_paper_size,
    parsedimen,
    parsedraw,
    simple_warning,
)
from psutils.pstops import pstops

VERSION = importlib.metadata.version("psutils")

VERSION_BANNER = f"""\
%(prog)s {VERSION}
Copyright (c) Reuben Thomas 2023.
Released under the GPL version 3, or (at your option) any later version.
"""


def parsenup(s: str) -> int:
    if not re.match(r"-\d+", s):
        die(f'value "{s}" invalid for -NUMBER (number expected)')
    n = -int(s)
    if n == 0:
        die("number of pages per sheet must be greater than 0")
    return n


class ToggleAction(argparse.Action):
    def __init__(
        self,
        option_strings: List[str],
        dest: str,
        nargs: Optional[str] = None,
        default: bool = False,
        **kwargs: Any,
    ) -> None:
        if nargs is not None:
            raise ValueError("nargs not allowed")
        super().__init__(option_strings, dest, nargs=0, default=default, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Union[str, Sequence[Any], None],
        option_string: Optional[str] = None,
    ) -> None:
        setattr(namespace, self.dest, not getattr(namespace, self.dest))


def get_parser() -> argparse.ArgumentParser:
    # Command-line arguments
    parser = argparse.ArgumentParser(
        description="Put multiple pages of a PostScript document on to one page.",
        formatter_class=HelpFormatter,
        usage="%(prog)s [OPTION...] -NUMBER [INFILE [OUTFILE]]",
        add_help=False,
        epilog="""
psnup aborts with an error if it cannot arrange the input pages so as to
waste less than the given tolerance.

The output page size defaults to the input page size; if that is not
given, the default given by the `paper' command is used.

The input page size defaults to the output page size.

In row-major order (the default), adjacent pages are placed in rows
across the paper; in column-major order, they are placed in columns down
the page.
""",
    )
    warnings.showwarning = simple_warning(parser.prog)

    # Command-line parser
    add_paper_arguments(parser)
    parser.add_argument(
        "-m",
        "--margin",
        metavar="DIMENSION",
        type=parsedimen,
        default=0,
        help="""\
width of margin around each output page
[default 0pt]; useful for thumbnail sheets,
as the original page margins will be shrunk""",
    )
    parser.add_argument(
        "-b",
        "--border",
        metavar="DIMENSION",
        type=parsedimen,
        default=0,
        help="width of border around each input page",
    )
    parser.add_argument(
        "-d",
        "--draw",
        metavar="DIMENSION",
        nargs="?",
        type=parsedraw,
        default=0,
        help="""\
draw a line of given width (relative to original
page) around each page [argument defaults to 1pt;
default is no line]""",
    )
    parser.add_argument(
        "-l",
        "--rotatedleft",
        action=ToggleAction,
        help="input pages are rotated left 90 degrees",
    )
    parser.add_argument(
        "-r",
        "--rotatedright",
        action=ToggleAction,
        help="input pages are rotated right 90 degrees",
    )
    parser.add_argument(
        "-f", "--flip", action=ToggleAction, help="swap output pages' width and height"
    )
    parser.add_argument(
        "-c",
        "--transpose",
        action=ToggleAction,
        help="swap columns and rows (column-major order)",
    )
    parser.add_argument(
        "-t",
        "--tolerance",
        metavar="NUMBER",
        type=int,
        default=100_000,
        help="maximum wasted area in square pt [default: %(default)s]",
    )
    parser.add_argument(
        "nup",
        metavar="-NUMBER",
        type=parsenup,
        help="number of pages to impose on each output page",
    )
    add_basic_arguments(parser, VERSION_BANNER)

    return parser


# pylint: disable=dangerous-default-value
def psnup(
    argv: List[str] = sys.argv[1:],
) -> None:
    args = get_parser().parse_intermixed_args(argv)
    size: Optional[Rectangle] = None
    in_size: Optional[Rectangle] = None
    if args.paper:
        size = args.paper
    elif args.width is not None and args.height is not None:
        size = Rectangle(args.width, args.height)
    if args.inpaper:
        in_size = args.inpaper
    elif args.inwidth is not None and args.inheight is not None:
        in_size = Rectangle(args.inwidth, args.inheight)
    else:
        with document_transform(
            args.infile,
            args.outfile,
            Rectangle(args.width, args.height),
            None,
            [],
            False,
            1.0,
            0,
        ) as transform:
            if transform.in_size is not None:
                in_size = Rectangle(transform.in_size.width, transform.in_size.height)

    # Process command-line arguments
    rowmajor, leftright, topbottom = True, True, True
    if args.transpose:
        rowmajor = False
    if args.rotatedleft:
        rowmajor = not rowmajor
        topbottom = not topbottom
    if args.rotatedright:
        rowmajor = not rowmajor
        leftright = not leftright

    if size is None and ((args.width is None) ^ (args.height is None)):
        die("output page width and height must both be set, or neither")
    if in_size is None and ((args.inwidth is None) ^ (args.inheight is None)):
        die("input page width and height must both be set, or neither")

    # Set output height/width from corresponding input value if undefined
    if size is None and in_size is not None:
        size = in_size

    # Ensure output page size is set
    if size is None:
        paper_size = get_paper_size()
        if paper_size is not None:
            size = paper_size
    if size is None:
        die("output page size not set, and could not get default paper size")

    # Set input height/width from corresponding output value if undefined
    if in_size is None:
        in_size = size
    assert in_size

    # Take account of flip
    if args.flip:
        size = Rectangle(size.height, size.width)

    # Find next larger exact divisor > n of m, or 0 if none; return divisor
    # and dividend.
    # There is probably a much more efficient method of doing this, but the
    # numbers involved are small.
    def nextdiv(n: int, m: int) -> Tuple[int, int]:
        while n < m:
            n += 1
            if m % n == 0:
                return n, m // n
        return 0, 0

    # Arguments for pstops
    cmd = []

    # Tell pstops input page size
    cmd.append(f"--inpaper={in_size.width}x{in_size.height}")

    # Add flags from our own input flags
    if not args.verbose:
        cmd.append("--quiet")
    if args.draw is not None:
        cmd.extend(["--draw", f"{args.draw}"])

    # Calculate paper dimensions, subtracting paper margin from height & width
    ppwid, pphgt = size.width - args.margin * 2, size.height - args.margin * 2
    if ppwid <= 0 or pphgt <= 0:
        die("margin is too large")
    if args.border > min(ppwid, pphgt):
        die("border is too large")

    # Finding the best layout is an optimisation problem. We try all of the
    # combinations of width*height in both normal and rotated form, and
    # minimise the wasted space.
    best = args.tolerance
    horiz: float
    vert: float
    rotate: float

    def reduce_waste(
        hor: float, ver: float, iwid: float, ihgt: float, rot: float
    ) -> None:
        nonlocal best, horiz, vert, rotate
        scl = min(pphgt / (ihgt * ver), ppwid / (iwid * hor))
        waste = (ppwid - scl * iwid * hor) ** 2 + (pphgt - scl * ihgt * ver) ** 2
        if waste < best:
            best, horiz, vert, rotate = waste, hor, ver, rot

    hor, ver = 1, args.nup
    while hor != 0:
        reduce_waste(hor, ver, in_size.width, in_size.height, 0)  # normal orientation
        reduce_waste(ver, hor, in_size.height, in_size.width, 1)  # rotated orientation
        hor, ver = nextdiv(hor, args.nup)

    # Fail if nothing better than tolerance was found
    if best == args.tolerance:
        die(f"can't find acceptable layout for {args.nup}-up")

    # Take account of rotation
    if rotate:
        topbottom, leftright, rowmajor, in_size.width, in_size.height = (
            not leftright,
            topbottom,
            not rowmajor,
            in_size.height,
            in_size.width,
        )

    # Calculate page scale, allowing for internal borders
    scale = min(
        (pphgt - 2 * args.border * vert) / (in_size.height * vert),
        (ppwid - 2 * args.border * horiz) / (in_size.width * horiz),
    )

    # Page centring shifts
    hshift, vshift = (ppwid / horiz - in_size.width * scale) / 2, (
        pphgt / vert - in_size.height * scale
    ) / 2

    cmd.append(f"--paper={size.width}x{size.height}")  # set output page size for pstops

    # Construct specification list
    specs = []
    for page in range(args.nup):
        across, up = (
            (page % horiz, page // horiz) if rowmajor else (page // vert, page % vert)
        )
        if not leftright:
            across = horiz - 1 - across
        if topbottom:
            up = vert - 1 - up
        if rotate:
            xoff = args.margin + (across + 1) * ppwid / horiz - hshift
        else:
            xoff = args.margin + across * ppwid / horiz + hshift
        yoff = args.margin + up * pphgt / vert + vshift
        specs.append(f'{page}{"L" if rotate else ""}@{scale:f}({xoff:f},{yoff:f})')

    # Rearrange pages
    cmd.extend(["--specs", f'{args.nup}:{"+".join(specs)}'])
    if args.infile is not None:
        cmd.append(args.infile)
    if args.outfile is not None:
        cmd.append(args.outfile)
    try:
        pstops(cmd)
    except SystemExit:
        die("error running pstops")


if __name__ == "__main__":
    psnup()
