"""Integration tests for the CSV and PDF pipelines."""

import io
import os
import sys
from pathlib import Path
import tempfile

import pytest

from deduce_pipeline import csv as csv_module
from deduce_pipeline import pdf as pdf_module
from reportlab.pdfgen import canvas


@pytest.fixture
def simple_csv(tmp_path):
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("name,age\nJohn Doe,45\n")
    return csv_path


@pytest.fixture
def simple_pdf(tmp_path):
    pdf_path = tmp_path / "input.pdf"
    # create a one‑page PDF with a single line of text
    c = canvas.Canvas(str(pdf_path))
    c.drawString(100, 750, "This is a test document.")
    c.showPage()
    c.save()
    return pdf_path


def check_output_file(path: Path):
    assert path.exists()
    assert path.stat().st_size > 0


def test_csv_pipeline(simple_csv, tmp_path):
    out_dir = tmp_path / "out"
    custom_pdf = out_dir / "custom.pdf"
    deduce_pdf = out_dir / "deduce.pdf"

    custom_out, deduce_out = csv_module.run_pipeline(
        input_csv=simple_csv,
        output_custom_pdf=custom_pdf,
        output_deduce_pdf=deduce_pdf,
        output_dir=out_dir,
        write_log_file=False,
    )
    assert custom_out == custom_pdf
    assert deduce_out == deduce_pdf
    check_output_file(custom_pdf)
    check_output_file(deduce_pdf)


def test_pdf_pipeline(simple_pdf, tmp_path):
    out_dir = tmp_path / "out"
    custom_pdf = out_dir / "custom.pdf"
    deduce_pdf = out_dir / "deduce.pdf"

    custom_out, deduce_out = pdf_module.run_pipeline(
        input_pdf=simple_pdf,
        output_custom_pdf=custom_pdf,
        output_deduce_pdf=deduce_pdf,
        output_dir=out_dir,
        write_log_file=False,
    )
    assert custom_out == custom_pdf
    assert deduce_out == deduce_pdf
    check_output_file(custom_pdf)
    check_output_file(deduce_pdf)


def test_command_line_entrypoints(tmp_path, simple_csv, simple_pdf, capsys):
    # call csv main via sys.argv simulation
    argv = ["--input", str(simple_csv), "--outdir", str(tmp_path), "--no-logfile"]
    rv = csv_module.main(argv)
    assert rv == 0
    # two output files should exist in tmp_path
    assert any(p.name.endswith("_custom.pdf") for p in tmp_path.iterdir())

    # pdf main
    argv = ["--input", str(simple_pdf), "--outdir", str(tmp_path), "--no-logfile"]
    rv = pdf_module.main(argv)
    assert rv == 0
    assert any(p.name.endswith("_deidentified_custom.pdf") for p in tmp_path.iterdir())


if __name__ == "__main__":
    pytest.main([__file__])