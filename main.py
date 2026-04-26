from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from review_engine.extractor import extract_zip_to_review_folder
from review_engine.classifier import detect_project_type
from review_engine.rubric_loader import load_rubric
from review_engine.evaluator import evaluate_rubric
from review_engine.feedback_generator import generate_feedback_markdown
from review_engine.llm_reviewer import (
    generate_llm_feedback,
    is_llm_mode,
    list_gemini_models,
    selected_llm_provider,
)
from review_engine.rubric_validator import validate_rubric_file
from review_engine.utils import write_json


def load_local_env(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Review Agent MVP")
    parser.add_argument("--zip", required=False, help="Path to student project zip file")
    parser.add_argument(
        "--validate-rubric",
        required=False,
        help="Validate a rubric YAML file and exit without reviewing a submission.",
    )
    parser.add_argument(
        "--list-gemini-models",
        action="store_true",
        help="List Gemini models available to the configured GEMINI_API_KEY and exit.",
    )
    parser.add_argument(
        "--rubric",
        required=False,
        help="Path to rubric YAML file. If omitted, use --auto-detect.",
    )
    parser.add_argument(
        "--auto-detect",
        action="store_true",
        help="Automatically detect project type and select rubric.",
    )
    parser.add_argument(
        "--mode",
        choices=["static_only", "runtime_local", "llm_assisted", "full_review"],
        default="static_only",
        help=(
            "Review mode. static_only inspects files only; runtime_local also "
            "runs rubric commands; llm_assisted/full_review reserve space for "
            "a future LLM judgment layer."
        ),
    )
    parser.add_argument(
        "--enable-runtime-checks",
        action="store_true",
        help=(
            "Legacy alias for --mode runtime_local. "
            "Only use this for submissions you are comfortable executing."
        ),
    )
    return parser.parse_args()


def copy_latest_outputs(feedback_md: Path, feedback_txt: Path) -> None:
    outputs_dir = Path("outputs")
    outputs_dir.mkdir(exist_ok=True)

    shutil.copyfile(feedback_md, outputs_dir / "latest_feedback.md")
    shutil.copyfile(feedback_txt, outputs_dir / "latest_feedback.txt")


def main() -> None:
    load_local_env()
    args = parse_args()
    if args.list_gemini_models:
        result = list_gemini_models()
        print(f"Status: {result['status']}")
        if result.get("reason"):
            print(f"Reason: {result['reason']}")

        models = [
            model for model in result.get("models", [])
            if model.get("supports_generate_content")
        ]
        if models:
            print("\nModels supporting generateContent:")
            for model in models:
                display_name = model.get("display_name") or ""
                print(f"- {model['model_id']} {display_name}".rstrip())
        elif result["status"] == "completed":
            print("\nNo models supporting generateContent were returned for this key.")

        if result["status"] != "completed":
            raise SystemExit(1)
        return

    if args.validate_rubric:
        rubric_path = Path(args.validate_rubric)
        validation = validate_rubric_file(rubric_path)
        print(f"Rubric: {rubric_path}")

        if validation["valid"]:
            print("Status: valid")
        else:
            print("Status: invalid")

        if validation["errors"]:
            print("\nErrors:")
            for error in validation["errors"]:
                print(f"- {error}")

        if validation["warnings"]:
            print("\nWarnings:")
            for warning in validation["warnings"]:
                print(f"- {warning}")

        if not validation["valid"]:
            raise SystemExit(1)
        return

    if not args.zip:
        raise ValueError("Please provide --zip, or use --validate-rubric.")

    zip_path = Path(args.zip)
    review_mode = "runtime_local" if args.enable_runtime_checks else args.mode

    if not zip_path.exists():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")

    review_dir, extracted_dir = extract_zip_to_review_folder(zip_path)

    if args.rubric:
        rubric_path = Path(args.rubric)
        detected = {
            "detected_project": "manual",
            "confidence": 1.0,
            "rubric_path": str(rubric_path),
            "evidence": ["Rubric was provided manually."],
        }
    elif args.auto_detect:
        detected = detect_project_type(extracted_dir)
        rubric_path = Path(detected["rubric_path"])
    else:
        raise ValueError("Please provide either --rubric or --auto-detect.")

    rubric = load_rubric(rubric_path)
    evaluation = evaluate_rubric(
        extracted_dir,
        rubric,
        review_mode=review_mode,
    )

    evidence_output = {
        "review_dir": str(review_dir),
        "submission_zip": str(zip_path),
        "review_mode": review_mode,
        "detected": detected,
        "evaluation": evaluation,
    }

    deterministic_feedback = generate_feedback_markdown(
        project_name=rubric["project_name"],
        detected=detected,
        evaluation=evaluation,
    )

    feedback = deterministic_feedback
    llm_result = {
        "status": "not_requested",
        "reason": None,
        "model": None,
    }

    if is_llm_mode(review_mode):
        llm_result = generate_llm_feedback(
            project_name=rubric["project_name"],
            evidence_output=evidence_output,
            deterministic_feedback=deterministic_feedback,
        )
        feedback = llm_result["feedback"]
        evaluation["summary"]["llm_status"] = llm_result["status"]
        evidence_output["llm_review"] = {
            key: value
            for key, value in llm_result.items()
            if key != "feedback"
        }
    else:
        evidence_output["llm_review"] = llm_result

    evidence_path = review_dir / "evidence.json"
    write_json(evidence_path, evidence_output)

    feedback_md = review_dir / "feedback.md"
    feedback_txt = review_dir / "feedback.txt"
    deterministic_feedback_md = review_dir / "deterministic_feedback.md"
    deterministic_feedback_txt = review_dir / "deterministic_feedback.txt"

    deterministic_feedback_md.write_text(deterministic_feedback, encoding="utf-8")
    deterministic_feedback_txt.write_text(deterministic_feedback, encoding="utf-8")
    feedback_md.write_text(feedback, encoding="utf-8")
    feedback_txt.write_text(feedback, encoding="utf-8")

    copy_latest_outputs(feedback_md, feedback_txt)

    print("\nReview complete.")
    print(f"Review folder: {review_dir}")
    print(f"Evidence: {evidence_path}")
    print(f"Feedback Markdown: {feedback_md}")
    print(f"Feedback TXT: {feedback_txt}")
    print("\nDetected project:")
    print(f"- {detected['detected_project']}")
    print(f"- Confidence: {detected['confidence']:.2f}")
    print(f"- Review mode: {review_mode}")
    if is_llm_mode(review_mode):
        print(f"- LLM provider: {llm_result.get('provider', selected_llm_provider())}")
        if llm_result.get("model"):
            print(f"- LLM model: {llm_result['model']}")
    print(f"- LLM status: {llm_result['status']}")
    if llm_result.get("reason"):
        print(f"- LLM note: {llm_result['reason']}")


if __name__ == "__main__":
    main()
