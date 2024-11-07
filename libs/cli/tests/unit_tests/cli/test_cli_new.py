"""Unit tests for the 'new' CLI command."""

import os
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

import requests
from click.testing import CliRunner

from langgraph_cli.cli import cli
from langgraph_cli.templates import TEMPLATE_ID_TO_CONFIG


@patch.object(requests, "get")
def test_create_new_with_mocked_download(mock_get: patch) -> None:
    """Test the 'new' CLI command with a mocked download response."""
    # Mock the response content to simulate a ZIP file
    mock_zip_content = BytesIO()
    with ZipFile(mock_zip_content, "w") as mock_zip:
        mock_zip.writestr("test-file.txt", "Test content.")
    mock_get.return_value.status_code = 200
    mock_get.return_value.content = mock_zip_content.getvalue()

    with TemporaryDirectory() as temp_dir:
        runner = CliRunner()
        template = next(
            iter(TEMPLATE_ID_TO_CONFIG)
        )  # Select the first template for the test
        result = runner.invoke(cli, ["new", temp_dir, "--template", template])

        # Verify CLI command execution and success
        assert result.exit_code == 0, result.output
        assert (
            "New project created" in result.output
        ), "Expected success message in output."

        # Verify that the directory is not empty
        assert os.listdir(temp_dir), "Expected files to be created in temp directory."

        # Check for a known file in the extracted content
        extracted_files = [f.name for f in Path(temp_dir).glob("*")]
        assert (
            "test-file.txt" in extracted_files
        ), "Expected 'test-file.txt' in the extracted content."


def test_invalid_template_id() -> None:
    """Test that an invalid template ID passed via CLI results in a graceful error."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["new", "dummy_path", "--template", "invalid-template-id"]
    )

    # Verify the command failed and proper message is displayed
    assert result.exit_code != 0, "Expected non-zero exit code for invalid template."
    assert (
        "Template 'invalid-template-id' not found" in result.output
    ), "Expected error message in output."
