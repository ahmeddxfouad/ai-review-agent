# AI Review Agent MVP

This is the first version of your rubric-based project review assistant.

It does **not** submit reviews automatically. It only:

1. Accepts a project `.zip`
2. Extracts it safely into a local review folder
3. Detects the project type
4. Runs static checks against a rubric
5. Generates evidence-based feedback in Markdown and TXT

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

## Usage

Put a student project zip inside:

```bash
submissions/student_project.zip
```

Then run:

```bash
python main.py --zip submissions/student_project.zip --auto-detect
```

Or force a specific rubric:

```bash
python main.py --zip submissions/student_project.zip --rubric rubrics/storefront_backend.yaml
```

## Output

The generated files will appear in:

```txt
reviews/<review_id>/evidence.json
reviews/<review_id>/feedback.md
reviews/<review_id>/feedback.txt
outputs/latest_feedback.md
outputs/latest_feedback.txt
```

## Current limitations

This MVP only runs static checks, such as:

- file exists
- text contains keywords
- package.json contains dependencies or scripts
- folder exists
- glob pattern exists

Runtime checks like `npm install`, `npm test`, Docker sandboxing, dashboard watching, and form filling will be added later.
