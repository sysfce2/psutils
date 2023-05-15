import os
import sys
import subprocess
import difflib
import shutil
from contextlib import ExitStack, contextmanager
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, List, Iterator, Optional, Union

import pytest
from pytest import CaptureFixture, mark, param


@dataclass
class GeneratedInput:
    paper: str
    pages: int
    border: int = 1


@dataclass
class Case:
    name: str
    args: List[str]
    input: Union[GeneratedInput, str]
    error: Optional[int] = None


@contextmanager
def pushd(path: os.PathLike[str]) -> Iterator[None]:
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)


def compare_text_files(
    output_file: os.PathLike[str], expected_file: os.PathLike[str]
) -> None:
    with ExitStack() as stack:
        out_fd = stack.enter_context(open(output_file, encoding="ascii"))
        exp_fd = stack.enter_context(open(expected_file, encoding="ascii"))
        output_lines = out_fd.readlines()
        expected_lines = exp_fd.readlines()
        diff = list(
            difflib.unified_diff(
                output_lines, expected_lines, str(output_file), str(expected_file)
            )
        )
        if len(diff) > 0:
            sys.stdout.writelines(diff)
            raise ValueError("test output does not match expected output")


def compare_binary_files(
    output_file: os.PathLike[str], expected_file: os.PathLike[str]
) -> None:
    with ExitStack() as stack:
        out_fd = stack.enter_context(open(output_file, "rb"))
        exp_fd = stack.enter_context(open(expected_file, "rb"))
        output = out_fd.read()
        expected = exp_fd.read()
        if output != expected:
            raise ValueError("test output does not match expected output")


def compare_strings(
    output: str, output_file: os.PathLike[str], expected_file: os.PathLike[str]
) -> None:
    with open(output_file, "w", encoding="ascii") as fd:
        fd.write(output)
    compare_text_files(output_file, expected_file)


def compare_bytes(
    output: bytes, output_file: os.PathLike[str], expected_file: os.PathLike[str]
) -> None:
    with open(output_file, "wb") as fd:
        fd.write(output)
    compare_binary_files(output_file, expected_file)


def file_test(
    function: Callable[[List[str]], None],
    case: Case,
    datadir: Path,
    capsys: CaptureFixture[str],
    datafiles: Path,
    file_type: str,
    regenerate_input: bool,
    regenerate_expected: bool,
) -> None:
    module_name = function.__name__
    expected_file = datadir / module_name / case.name / "expected"
    expected_stderr = datadir / module_name / case.name / "expected-stderr.txt"
    if isinstance(case.input, str):
        test_file = datadir / case.input
    else:
        basename = f"{case.input.paper}-{case.input.pages}"
        if case.input.border != 1:
            basename += f"-{case.input.border}"
        test_file = datadir / basename
    if regenerate_input and isinstance(case.input, GeneratedInput):
        make_test_input(
            case.input.paper, case.input.pages, test_file, case.input.border
        )
    output_file = datafiles / "output"
    full_args = [*case.args, str(test_file.with_suffix(file_type)), str(output_file)]
    with pushd(datafiles):
        if case.error is None:
            assert expected_file is not None
            function(full_args)
            if regenerate_expected:
                shutil.copyfile(output_file, expected_file.with_suffix(file_type))
            else:
                comparer = (
                    compare_text_files if file_type == ".ps" else compare_binary_files
                )
                comparer(output_file, expected_file.with_suffix(file_type))
        else:
            with pytest.raises(SystemExit) as e:
                function(full_args)
            assert e.type == SystemExit
            assert e.value.code == case.error
        if regenerate_expected:
            with open(expected_stderr, "w", encoding="utf-8") as fd:
                fd.write(capsys.readouterr().err)
        else:
            compare_strings(
                capsys.readouterr().err, datafiles / "stderr.txt", expected_stderr
            )


def make_tests(
    function: Callable[..., Any],
    fixture_dir: Path,
    *tests: Case,
) -> Any:
    ids = []
    test_cases = []
    for t in tests:
        ids.append(t.name)
        test_cases.append(t)
    return mark.parametrize(
        "function,case,datadir",
        [
            param(
                function,
                case,
                fixture_dir,
                marks=mark.datafiles,
            )
            for case in test_cases
        ],
        ids=ids,
    )


# Make a test PostScript or PDF file of a given number of pages
# Requires a2ps and ps2pdf
# Simply writes a large page number on each page
def make_test_input(
    paper: str, pages: int, file: Path, border: Optional[int] = 1
) -> None:
    # Configuration
    lines_per_page = 4

    # Produce PostScript
    title = file.stem
    text = ("\n" * lines_per_page).join([str(i + 1) for i in range(pages)])
    subprocess.run(
        [
            "a2ps",
            f"--medium={paper}",
            f"--title={title}",
            f"--lines-per-page={lines_per_page}",
            "--portrait",
            "--columns=1",
            "--rows=1",
            f"--border={border}",
            "--no-header",
            f"--output={file.with_suffix('.ps')}",
        ],
        text=True,
        input=text,
        check=True,
    )

    # Convert to PDF if required
    if file.suffix == ".pdf":
        subprocess.check_call(
            [
                "ps2pdf",
                f"-sPAPERSIZE={paper}",
                f"{file.with_suffix('.ps')}",
                f"{file.with_suffix('.pdf')}",
            ]
        )
        os.remove(f"{file.with_suffix('.ps')}")
