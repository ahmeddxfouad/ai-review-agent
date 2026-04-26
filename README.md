# AI Review Agent MVP

This is a rubric-first project review assistant.

It is designed to help draft structured review feedback from a submitted project
ZIP. It does not submit reviews automatically, and a human reviewer should still
spot-check the final output before using it.

## Current Status

The agent currently supports:

1. Accepting a submitted project `.zip`
2. Safely extracting it into a timestamped local review folder
3. Detecting the project type or using a manually selected rubric
4. Running rubric-based static checks
5. Optionally running local runtime commands from the rubric
6. Capturing evidence for each check
7. Generating feedback in Markdown and TXT
8. Optionally refining feedback with an LLM using `evidence.json`

The Storefront Backend rubric is the most complete rubric right now. It includes
review categories for README setup, `REQUIREMENTS.md`, database schema,
migrations, SQL/model evidence, Express routes, TypeScript quality,
environment variables, JWT, bcrypt, endpoint tests, model tests, and local
runtime verification.

## Safety Notes

ZIP extraction is hardened against common unsafe archive behavior, including:

- path traversal entries such as `../file`
- absolute paths
- ZIP symlinks
- very large uncompressed archives
- archives with too many files

Runtime checks are disabled by default. Use runtime mode only for submissions you
are comfortable executing locally.

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

## Local Secrets

Create a local `.env` file for API keys and provider settings. This file is
ignored by git.

```txt
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_key_here
GEMINI_MODEL=gemini-2.0-flash
```

The app loads `.env` automatically when it starts. Values already set in your
terminal environment take priority over `.env`.

## Basic Usage

Put a student project ZIP inside `submissions/`.

Example:

```txt
submissions/sample_storefront_project.zip
```

Run with automatic project detection:

```bash
python main.py --zip submissions/sample_storefront_project.zip --auto-detect
```

Or force a specific rubric:

```bash
python main.py --zip submissions/sample_storefront_project.zip --rubric rubrics/storefront_backend.yaml
```

Validate a rubric without reviewing a submission:

```bash
python main.py --validate-rubric rubrics/storefront_backend.yaml
```

List Gemini models available to your configured key:

```bash
python main.py --list-gemini-models
```

Use one of the listed model IDs for `GEMINI_MODEL`.

## Review Modes

The agent supports these modes:

- `static_only`: inspect files without running submitted code.
- `runtime_local`: inspect files and run rubric `run_command` checks locally.
- `llm_assisted`: inspect files and ask an LLM to refine the feedback from evidence.
- `full_review`: run static checks, local runtime checks, and LLM-assisted feedback.

Static review:

```bash
python main.py --zip submissions/sample_storefront_project.zip --rubric rubrics/storefront_backend.yaml --mode static_only
```

Local runtime review:

```bash
python main.py --zip submissions/sample_storefront_project.zip --rubric rubrics/storefront_backend.yaml --mode runtime_local
```

LLM-assisted review:

```bash
python main.py --zip submissions/sample_storefront_project.zip --rubric rubrics/storefront_backend.yaml --mode llm_assisted
```

You can optionally choose a Gemini model:

```bash
$env:GEMINI_MODEL="gemini-2.0-flash"
```

`llm_assisted` does not run submitted code. It sends the collected evidence and
deterministic feedback draft to the selected LLM provider, then writes the
LLM-refined feedback as the final `feedback.md`.

Supported LLM providers:

- `gemini`: uses the Gemini `generateContent` REST API.
- `openai`: uses the OpenAI Responses API.
- `none`: skips the LLM pass and keeps deterministic feedback.

Provider configuration examples:

```bash
$env:LLM_PROVIDER="gemini"
$env:GEMINI_API_KEY="your_gemini_key_here"
$env:GEMINI_MODEL="gemini-2.0-flash"
```

```bash
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="your_openai_key_here"
$env:OPENAI_MODEL="gpt-4o-mini"
```

`full_review` combines local runtime checks and LLM-assisted feedback:

```bash
python main.py --zip submissions/sample_storefront_project.zip --rubric rubrics/storefront_backend.yaml --mode full_review
```

`runtime_local` currently runs rubric checks of type `run_command`. In the
Storefront Backend rubric, the runtime section runs:

```txt
npm install
npm test
```

The legacy flag `--enable-runtime-checks` is still accepted as an alias for
`--mode runtime_local`.

## Rubric Checks

Rubrics are intentionally project-specific. The engine does not require all
projects to share one rubric. Instead, each rubric should describe its own
sections, checks, feedback, and references.

Before using or committing a rubric, validate it:

```bash
python main.py --validate-rubric rubrics/storefront_backend.yaml
```

The validator checks for:

- required top-level fields
- required section fields
- duplicate section or check IDs
- unsupported check types
- missing required check fields
- invalid `pass_rule`, `mode`, or review `modes`
- malformed runtime commands
- malformed route definitions
- missing feedback text warnings

Current static check types include:

- `file_exists`
- `folder_exists`
- `glob_exists`
- `text_contains_any`
- `text_contains_all`
- `package_json_has_dependency`
- `package_json_has_script`
- `file_list_contains_any`
- `file_list_contains_all`
- `code_contains_pattern`
- `code_contains_all_patterns`
- `json_file_contains_keys`
- `dependency_file_contains`
- `gitignore_contains`
- `route_pattern_exists`

Runtime check type:

- `run_command`

Example runtime check:

```yaml
- id: npm_test
  type: run_command
  command:
    - npm
    - test
  timeout_seconds: 180
  expected_exit_code: 0
  description: npm test completes successfully
```

Runtime commands must be argument lists, not shell strings.

The newer generic checks are intended to make the engine reusable across many
project rubrics. For example:

```yaml
- id: flask_dependencies
  type: dependency_file_contains
  path: requirements.txt
  dependencies:
    - Flask
    - SQLAlchemy
  mode: all
```

```yaml
- id: auth_calls
  type: code_contains_all_patterns
  patterns:
    - jwt.sign
    - jwt.verify
  file_patterns:
    - "**/*.ts"
    - "**/*.js"
```

```yaml
- id: api_routes
  type: route_pattern_exists
  routes:
    - method: GET
      path: /products
    - method: POST
      path: /products
```

## Output

Each run creates a timestamped review folder:

```txt
reviews/<review_id>/evidence.json
reviews/<review_id>/deterministic_feedback.md
reviews/<review_id>/deterministic_feedback.txt
reviews/<review_id>/feedback.md
reviews/<review_id>/feedback.txt
```

The latest feedback is also copied to:

```txt
outputs/latest_feedback.md
outputs/latest_feedback.txt
```

`evidence.json` records the full machine-readable review result, including:

- selected review mode
- detected project/rubric
- pass/fail status per section
- skipped sections
- static evidence
- runtime command output when runtime mode is used
- LLM status, model, response id, or skip/failure reason when LLM mode is used

## Important Limitation

Static checks can prove that files, text, dependencies, or patterns were found.
They cannot prove that the project works at runtime.

Runtime checks can prove that a command ran and returned a specific exit code,
but they still need a careful reviewer to interpret failures and decide whether
the rubric requirement is truly met.

The LLM layer uses the collected evidence to improve feedback quality. It should
not claim that code ran unless the runtime evidence says it ran. If the selected
provider key is missing or the API call fails, the agent keeps the deterministic
feedback and records the LLM status in `evidence.json`.

## Next Steps

Planned improvements:

- add code-aware checks for Express routes and HTTP methods
- detect model methods such as `index`, `show`, `create`, `update`, and `delete`
- detect SQL query types and parameterized queries
- detect `bcrypt.hash`, `bcrypt.compare`, `jwt.sign`, and `jwt.verify`
- compare endpoint tests against routes listed in `REQUIREMENTS.md`
- add Docker-based sandboxing for safer runtime execution
- add structured JSON output for the LLM layer
- add retry/backoff controls for LLM API calls
