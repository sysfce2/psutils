import importlib.metadata
import argparse
import re
import sys
import warnings
from typing import List, NoReturn, Optional, Tuple

from psutils import (
    HelpFormatter,
    add_basic_arguments,
    add_paper_arguments,
    die,
    parsedraw,
    singledimen,
    simple_warning,
    PageSpec,
    Range,
    PageList,
    page_index_to_page_number,
    documentTransform,
)

VERSION = importlib.metadata.version("psutils")

version_banner = f"""\
%(prog)s {VERSION}
Copyright (c) Reuben Thomas 2023.
Released under the GPL version 3, or (at your option) any later version.
"""

# Globals
scale = 1.0  # global scale factor
rotate = 0  # global rotation


# Command-line parsing helper functions
def specerror() -> NoReturn:
    die(
        """bad page specification:

  PAGESPECS = [MODULO:]SPEC
  SPEC      = [-]PAGENO[@SCALE][L|R|U|H|V][(XOFF,YOFF)][,SPEC|+SPEC]
              MODULO >= 1; 0 <= PAGENO < MODULO"""
    )


def parsespecs(
    s: str, width: Optional[float], height: Optional[float]
) -> Tuple[List[List[PageSpec]], int, bool]:
    flipping = False
    m = re.match(r"(?:([^:]+):)?(.*)", s)
    if not m:
        specerror()
    modulo, specs_text = int(m[1] or "1"), m[2]
    # Split on commas but not inside parentheses.
    pages_text = re.split(r",(?![^()]*\))", specs_text)
    pages = []
    angle = {"l": 90, "r": -90, "u": 180}
    for page in pages_text:
        specs = []
        specs_text = page.split("+")
        for spec_text in specs_text:
            m = re.match(
                r"(-)?(\d+)([LRUHV]+)?(?:@([^()]+))?(?:\((-?[\d.a-z]+),(-?[\d.a-z]+)\))?$",
                spec_text,
                re.IGNORECASE | re.ASCII,
            )
            if not m:
                specerror()
            spec = PageSpec()
            if m[1] is not None:
                spec.reversed = True
            if m[2] is not None:
                spec.pageno = int(m[2])
            if m[4] is not None:
                spec.scale = float(m[4])
            if m[5] is not None:
                spec.xoff = singledimen(m[5], width, height)
            if m[6] is not None:
                spec.yoff = singledimen(m[6], width, height)
            if spec.pageno >= modulo:
                specerror()
            if m[3] is not None:
                for mod in m[3]:
                    if re.match(r"[LRU]", mod, re.IGNORECASE):
                        spec.rotate += angle[mod.lower()]
                    elif re.match(r"H", mod, re.IGNORECASE):
                        spec.hflip = not spec.hflip
                    elif re.match(r"V", mod, re.IGNORECASE):
                        spec.vflip = not spec.vflip
            # Normalize rotation and flips
            if spec.hflip and spec.vflip:
                spec.hflip, spec.vflip = False, False
                spec.rotate += 180
            spec.rotate %= 360
            if spec.hflip or spec.vflip:
                flipping = True
            specs.append(spec)
        pages.append(specs)
    return pages, modulo, flipping


def parserange(ranges_text: str) -> List[Range]:
    ranges = []
    for range_text in ranges_text.split(","):
        r = Range()
        if range_text == "_":
            r.start, r.end = 0, 0  # so page_to_real_page() returns -1
        else:
            m = re.match(r"(_?\d+)?(?:(-)(_?\d+))?$", range_text)
            if not m:
                die(f"`{range_text}' is not a page range")
            start = m[1] or "1"
            end = (m[3] or "-1") if m[2] else m[1]
            start = re.sub("^_", "-", start)
            end = re.sub("^_", "-", end)
            r.start, r.end = int(start), int(end)
        r.text = range_text
        ranges.append(r)
    return ranges


def get_parser() -> argparse.ArgumentParser:
    # Command-line arguments
    parser = argparse.ArgumentParser(
        description="Rearrange pages of a PDF or PostScript document.",
        formatter_class=HelpFormatter,
        usage="%(prog)s [OPTION...] [INFILE [OUTFILE]]",
        add_help=False,
        epilog="""
PAGES is a comma-separated list of pages and page ranges.

SPECS is a list of page specifications [default is "0", which selects
each page in its normal order].
""",
    )
    warnings.showwarning = simple_warning(parser.prog)

    # Command-line parser
    parser.add_argument(
        "-S",
        "--specs",
        default="0",
        help="page specifications (see below)",
    )
    parser.add_argument(
        "-R",
        "--pages",
        dest="pagerange",
        type=parserange,
        help="select the given page ranges",
    )
    parser.add_argument(
        "-e",
        "--even",
        action="store_true",
        help="select even-numbered output pages",
    )
    parser.add_argument(
        "-o",
        "--odd",
        action="store_true",
        help="select odd-numbered output pages",
    )
    parser.add_argument(
        "-r",
        "--reverse",
        action="store_true",
        help="reverse the order of the output pages",
    )
    add_paper_arguments(parser)
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
    parser.add_argument("-b", "--nobind", help=argparse.SUPPRESS)
    add_basic_arguments(parser, version_banner)

    return parser


# pylint: disable=dangerous-default-value
def pstops(
    argv: List[str] = sys.argv[1:],
) -> None:
    args = get_parser().parse_intermixed_args(argv)
    width: Optional[float] = None
    height: Optional[float] = None
    iwidth: Optional[float] = None
    iheight: Optional[float] = None
    if args.paper:
        width, height = args.paper
    elif args.width is not None and args.height is not None:
        width, height = args.width, args.height
        if (width is None) ^ (height is None):
            die("output page width and height must both be set, or neither")
    if args.inpaper:
        iwidth, iheight = args.inpaper
    elif args.inwidth is not None and args.inheight is not None:
        iwidth, iheight = args.inwidth, args.inheight
        if (iwidth is None) ^ (iheight is None):
            die("input page width and height must both be set, or neither")
    specs, modulo, flipping = parsespecs(args.specs, width, height)

    with documentTransform(
        args.infile,
        args.outfile,
        width,
        height,
        iwidth,
        iheight,
        specs,
        rotate,
        scale,
        args.draw,
    ) as doc:
        if doc.iwidth is None and flipping:
            die("input page size must be set when flipping the page")

        # Page spec routines for page rearrangement
        def abs_page(n: int) -> int:
            if n < 0:
                n += doc.pages() + 1
                n = max(n, 1)
            return n

        def transform_pages(
            pagerange: List[Range], odd: bool, even: bool, reverse: bool
        ) -> None:
            outputpage = 0
            # If no page range given, select all pages
            if pagerange is None:
                pagerange = parserange("1-_1")

            # Normalize end-relative pageranges
            for r in pagerange:
                r.start = abs_page(r.start)
                r.end = abs_page(r.end)

            # Get list of pages
            page_list = PageList(doc.pages(), pagerange, reverse, odd, even)

            # Calculate highest page number output (including any blanks)
            maxpage = (
                page_list.num_pages()
                + (modulo - page_list.num_pages() % modulo) % modulo
            )

            # Rearrange pages
            doc.write_header(maxpage, modulo)
            pagebase = 0
            while pagebase < maxpage:
                for page in doc.specs:
                    # Construct the page label from the input page numbers
                    pagelabels = []
                    for spec in page:
                        n = page_list.real_page(
                            page_index_to_page_number(spec, maxpage, modulo, pagebase)
                        )
                        pagelabels.append(str(n + 1) if n >= 0 else "*")
                    pagelabel = ",".join(pagelabels)
                    outputpage += 1
                    doc.write_page_comment(pagelabel, outputpage)
                    if args.verbose:
                        sys.stderr.write(f"[{pagelabel}] ")
                    doc.write_page(
                        page_list, outputpage, page, maxpage, modulo, pagebase
                    )

                pagebase += modulo

            doc.finalize()
            if args.verbose:
                print(f"\nWrote {outputpage} pages", file=sys.stderr)

        # Output the pages
        transform_pages(args.pagerange, args.odd, args.even, args.reverse)


if __name__ == "__main__":
    pstops()
