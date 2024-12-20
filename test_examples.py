import pytest
import subprocess
import os

EXAMPLES_DIR = "examples"

assert os.environ.get('OPENAI_API_KEY') is not None, "OPENAI_API_KEY environment variable is not set"


example_files = []
for file in os.listdir(EXAMPLES_DIR):
    if file.endswith(".py"):
        example_files.append(file)

@pytest.mark.using_external_apis
@pytest.mark.parametrize("example_file", example_files)
def test_example_script(example_file):
    example_path = os.path.join(EXAMPLES_DIR, example_file)
    result = subprocess.run(["python", example_path], capture_output=True, text=True)
    assert result.returncode == 0, f"Example {example_file} failed with output: {result.stderr}"

