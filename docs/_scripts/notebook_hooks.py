import logging
import os
import re
import traceback
from typing import Any, Callable, Dict

from markdown import Markdown
from pymdownx.superfences import SuperFencesException
from mkdocs.structure.files import Files, File
from mkdocs.structure.pages import Page
import posixpath

from markdown_exec.hooks import SessionHistoryEntry

from generate_api_reference_links import update_markdown_with_imports
from notebook_convert import convert_notebook
from setup_vcr import load_postamble, load_preamble, _hash_string

logger = logging.getLogger(__name__)
logging.basicConfig()
logger.setLevel(logging.INFO)
DISABLED = os.getenv("DISABLE_NOTEBOOK_CONVERT") in ("1", "true", "True")


REDIRECT_MAP = {
    # lib redirects
    "how-tos/stream-values.ipynb": "how-tos/streaming.ipynb#values",
    "how-tos/stream-updates.ipynb": "how-tos/streaming.ipynb#updates",
    "how-tos/streaming-content.ipynb": "how-tos/streaming.ipynb#custom",
    "how-tos/stream-multiple.ipynb": "how-tos/streaming.ipynb#multiple",
    "how-tos/streaming-tokens-without-langchain.ipynb": "how-tos/streaming-tokens.ipynb#example-without-langchain",
    "how-tos/streaming-from-final-node.ipynb": "how-tos/streaming-specific-nodes.ipynb",
    "how-tos/streaming-events-from-within-tools-without-langchain.ipynb": "how-tos/streaming-events-from-within-tools.ipynb#example-without-langchain",
    # cloud redirects
    "cloud/index.md": "concepts/index.md#langgraph-platform",
    "cloud/how-tos/index.md": "how-tos/index.md#langgraph-platform",
    "cloud/concepts/api.md": "concepts/langgraph_server.md",
    "cloud/concepts/cloud.md": "concepts/langgraph_cloud.md",
    "cloud/faq/studio.md": "concepts/langgraph_studio.md#studio-faqs",
}


class NotebookFile(File):
    def is_documentation_page(self):
        return True


def on_files(files: Files, **kwargs: Dict[str, Any]):
    if DISABLED:
        return files
    new_files = Files([])
    for file in files:
        if file.src_path.endswith(".ipynb"):
            new_file = NotebookFile(
                path=file.src_path,
                src_dir=file.src_dir,
                dest_dir=file.dest_dir,
                use_directory_urls=file.use_directory_urls,
            )
            new_files.append(new_file)
        else:
            new_files.append(file)
    return new_files


def _add_path_to_code_blocks(markdown: str, page: Page) -> str:
    """Add the path to the code blocks."""
    code_block_pattern = re.compile(
        r"(?P<indent>[ \t]*)```(?P<language>\w+)[ ]*(?P<attributes>[^\n]*)\n"
        r"(?P<code>((?:.*\n)*?))"  # Capture the code inside the block using named group
        r"(?P=indent)```"  # Match closing backticks with the same indentation
    )

    def replace_code_block_header(match: re.Match) -> str:
        indent = match.group("indent")
        language = match.group("language")
        attributes = match.group("attributes").rstrip()

        if 'exec="on"' not in attributes:
            # Return original code block
            return match.group(0)

        code = match.group("code")
        return f'{indent}```{language} {attributes} path="{page.file.src_path}"\n{code}{indent}```'

    return code_block_pattern.sub(replace_code_block_header, markdown)


def _highlight_code_blocks(markdown: str) -> str:
    """Find code blocks with highlight comments and add hl_lines attribute.

    Args:
        markdown: The markdown content to process.

    Returns:
        updated Markdown code with code blocks containing highlight comments
        updated to use the hl_lines attribute.
    """
    # Pattern to find code blocks with highlight comments and without
    # existing hl_lines for Python and JavaScript
    # Pattern to find code blocks with highlight comments, handling optional indentation
    code_block_pattern = re.compile(
        r"(?P<indent>[ \t]*)```(?P<language>py|python|js|javascript)(?!\s+hl_lines=)\n"
        r"(?P<code>((?:.*\n)*?))"  # Capture the code inside the block using named group
        r"(?P=indent)```"  # Match closing backticks with the same indentation
    )

    def replace_highlight_comments(match: re.Match) -> str:
        indent = match.group("indent")
        language = match.group("language")
        code_block = match.group("code")
        lines = code_block.split("\n")
        highlighted_lines = []

        # Skip initial empty lines
        while lines and not lines[0].strip():
            lines.pop(0)

        lines_to_keep = []

        comment_syntax = (
            "# highlight-next-line"
            if language in ["py", "python"]
            else "// highlight-next-line"
        )

        for line in lines:
            if comment_syntax in line:
                count = len(lines_to_keep) + 1
                highlighted_lines.append(str(count))
            else:
                lines_to_keep.append(line)

        # Reconstruct the new code block
        new_code_block = "\n".join(lines_to_keep)

        if highlighted_lines:
            return (
                f'{indent}```{language} hl_lines="{" ".join(highlighted_lines)}"\n'
                # The indent and terminating \n is already included in the code block
                f"{new_code_block}"
                f"{indent}```"
            )
        else:
            return (
                f"{indent}```{language}\n"
                # The indent and terminating \n is already included in the code block
                f"{new_code_block}"
                f"{indent}```"
            )

    # Replace all code blocks in the markdown
    markdown = code_block_pattern.sub(replace_highlight_comments, markdown)
    return markdown


def handle_vcr_setup(
    *,
    formatter: Callable,
    language: str,
    code: str,
    session: str,
    id: str,
    md: Markdown,
    **kwargs: Dict[str, Any],
) -> str:
    """Handle VCR setup in markdown content if necessary."""
    try:
        if kwargs.get("extra", None) is None:
            raise ValueError(
                f"error while processing {language} block: extra dict is required"
            )

        if kwargs["extra"].get("path", None) is None:
            raise ValueError(
                f"error while processing {language} block: path is required"
            )

        document_filename = kwargs["extra"]["path"]

        if session is None or session == "" and id is None or id == "":
            id = _hash_string(code)

        if session is not None and session != "":
            logger.info(f"new session {session} on page {document_filename}")

        cassette_prefix = document_filename.replace(".md", "").replace(os.path.sep, "_")

        cassette_dir = os.path.abspath(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "cassettes")
        )
        os.makedirs(cassette_dir, exist_ok=True)

        # Build a unique cassette name.
        cassette_name = os.path.join(
            cassette_dir,
            f"{cassette_prefix}_{session if session else id}_{language}.msgpack.zlib",
        )

        # Add context manager at start with explicit __enter__ and __exit__ calls

        wrapped_lines = [
            load_preamble(language, code, cassette_name),
            code,
        ]

        if session is None or session == "":
            logger.info(
                f"no session, adding postamble for {language} in {document_filename}"
            )
            wrapped_lines.append(load_postamble(language))

        transformed_source = "\n".join(wrapped_lines)
        return dict(
            transform_source=lambda code: (transformed_source, code),
            id=id,
            extra={},
        )
    except Exception as e:
        raise SuperFencesException(traceback.format_exc()) from e


def handle_vcr_teardown(
    *,
    formatter: Callable,
    language: str,
    session: str,
    history: list[SessionHistoryEntry],
):
    session = history[-1].inputs["session"]
    last_inputs = dict(history[-1].inputs)
    code = load_postamble(language)
    md = last_inputs["md"]
    html = False
    update_toc = False
    session = last_inputs.get("session", None)

    document_filename = last_inputs.get("extra", {}).get("path", None)

    if document_filename is None:
        logger.warning(f"no document filename found while tearing down {session}!")
    else:
        logger.info(f"tearing down {session} on {document_filename}")
        logger.info(traceback.format_stack())

    kwargs = dict(
        code=code,
        session=session,
        id=f"{id}_vcr_end",
        md=md,
        html=html,
        update_toc=update_toc,
        extra={},
    )

    # This doesn't actually render anything, we just call the formatter so it
    # executes in the same context as the session of which we're disposing.
    formatter(**kwargs)


def _on_page_markdown_with_config(
    markdown: str,
    page: Page,
    *,
    add_api_references: bool = True,
    remove_base64_images: bool = False,
    **kwargs: Any,
) -> str:
    if DISABLED:
        return markdown

    if page.file.src_path.endswith(".ipynb"):
        # logger.info("Processing Jupyter notebook: %s", page.file.src_path)
        markdown = convert_notebook(page.file.abs_src_path)

    # Append API reference links to code blocks
    if add_api_references:
        markdown = update_markdown_with_imports(markdown)
    # Apply highlight comments to code blocks
    markdown = _highlight_code_blocks(markdown)

    # Add file path as an attribute to code blocks that are executable.
    # This file path is used to associate fixtures with the executable code
    # which can be used in CI to test the docs without making network requests.
    markdown = _add_path_to_code_blocks(markdown, page)

    if remove_base64_images:
        # Remove base64 encoded images from markdown
        markdown = re.sub(r"!\[.*?\]\(data:image/[^;]+;base64,[^\)]+\)", "", markdown)

    return markdown


def on_page_markdown(markdown: str, page: Page, **kwargs: Dict[str, Any]):
    return _on_page_markdown_with_config(
        markdown,
        page,
        add_api_references=True,
        **kwargs,
    )


# redirects

HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Redirecting...</title>
    <link rel="canonical" href="{url}">
    <meta name="robots" content="noindex">
    <script>var anchor=window.location.hash.substr(1);location.href="{url}"+(anchor?"#"+anchor:"")</script>
    <meta http-equiv="refresh" content="0; url={url}">
</head>
<body>
Redirecting...
</body>
</html>
"""


def write_html(site_dir, old_path, new_path):
    """Write an HTML file in the site_dir with a meta redirect to the new page"""
    # Determine all relevant paths
    old_path_abs = os.path.join(site_dir, old_path)
    old_dir_abs = os.path.dirname(old_path_abs)

    # Create parent directories if they don't exist
    if not os.path.exists(old_dir_abs):
        os.makedirs(old_dir_abs)

    # Write the HTML redirect file in place of the old file
    content = HTML_TEMPLATE.format(url=new_path)
    with open(old_path_abs, "w", encoding="utf-8") as f:
        f.write(content)


# Create HTML files for redirects after site dir has been built
def on_post_build(config):
    use_directory_urls = config.get("use_directory_urls")
    for page_old, page_new in REDIRECT_MAP.items():
        page_old = page_old.replace(".ipynb", ".md")
        page_new = page_new.replace(".ipynb", ".md")
        page_new_before_hash, hash, suffix = page_new.partition("#")
        old_html_path = File(page_old, "", "", use_directory_urls).dest_path.replace(
            os.sep, "/"
        )
        new_html_path = File(page_new_before_hash, "", "", True).url
        new_html_path = (
            posixpath.relpath(new_html_path, start=posixpath.dirname(old_html_path))
            + hash
            + suffix
        )
        write_html(config["site_dir"], old_html_path, new_html_path)
