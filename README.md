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

## Review Modes

The agent supports these modes:

- `static_only`: inspect files without running submitted code.
- `runtime_local`: inspect files and run rubric `run_command` checks locally.
- `llm_assisted`: reserved for a future LLM judgment layer.
- `full_review`: reserved for static checks, local runtime checks, and future LLM-assisted feedback.

Static review:

```bash
python main.py --zip submissions/sample_storefront_project.zip --rubric rubrics/storefront_backend.yaml --mode static_only
```

Local runtime review:

```bash
python main.py --zip submissions/sample_storefront_project.zip --rubric rubrics/storefront_backend.yaml --mode runtime_local
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

## Output

Each run creates a timestamped review folder:

```txt
reviews/<review_id>/evidence.json
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

## Important Limitation

Static checks can prove that files, text, dependencies, or patterns were found.
They cannot prove that the project works at runtime.

Runtime checks can prove that a command ran and returned a specific exit code,
but they still need a careful reviewer to interpret failures and decide whether
the rubric requirement is truly met.

The planned LLM layer should use the collected evidence to improve feedback
quality. It should not claim that code ran unless the runtime evidence says it
ran.

## Next Steps

Planned improvements:

- add code-aware checks for Express routes and HTTP methods
- detect model methods such as `index`, `show`, `create`, `update`, and `delete`
- detect SQL query types and parameterized queries
- detect `bcrypt.hash`, `bcrypt.compare`, `jwt.sign`, and `jwt.verify`
- compare endpoint tests against routes listed in `REQUIREMENTS.md`
- add Docker-based sandboxing for safer runtime execution
- add the LLM-assisted review layer using `evidence.json`
