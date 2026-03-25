import pytest

from kairos.cli import main


def test_import_kairos():
    """Verify that the kairos package can be imported successfully."""
    import kairos

    assert kairos is not None


@pytest.mark.parametrize(
    "subcommand",
    ["embed", "check-staleness", "aggregate", "serve"],
)
def test_cli_help(subcommand, capsys):
    """Verify that each subcommand responds to --help with usage info."""
    with pytest.raises(SystemExit) as exc_info:
        main([subcommand, "--help"])

    # argparse exits with code 0 on --help
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert subcommand in captured.out
    assert "usage:" in captured.out.lower()


def test_cli_no_args(capsys):
    """Verify that running kairos with no arguments prints help and exits 0."""
    exit_code = main([])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "kairos" in captured.out.lower()
