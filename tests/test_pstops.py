from pathlib import Path

from testutils import file_test, make_tests, Case, GeneratedInput
from psutils.pstops import pstops

pytestmark = make_tests(
    pstops,
    Path(__file__).parent.resolve() / "test-files",
    Case(
        "offsets",
        ["--specs", "0(100pt,200pt)"],
        GeneratedInput("a4", 1),
    ),
    Case(
        "negative-offsets",
        ["--specs", "0(-100pt,-200pt)"],
        GeneratedInput("a4", 1),
    ),
    Case(
        "correct-angles",
        ["-pa4", "--specs", "0L(1w,0)+0R(0,1h)"],
        GeneratedInput("a5", 1),
    ),
    Case(
        "multiple-pages",
        ["--specs", "2:0(100pt,200pt),1(-200pt,100pt)"],
        GeneratedInput("a4", 2),
    ),
    Case(
        "multiple-turns-and-flips",
        ["-P", "a4", "--specs", "0LLRVHVHV(700pt,0pt)"],
        GeneratedInput("a4", 1),
    ),
    Case(
        "invalid-pagespecs",
        ["--specs=foo"],
        GeneratedInput("a4", 1),
        1,
    ),
    Case(
        "texlive",
        ["-pa4", "--specs", "2:0L@.7(21cm,0)+1L@.7(21cm,14.85cm)"],
        GeneratedInput("a4", 11),
    ),
)
test_pstops = file_test
