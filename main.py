from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from review_engine.extractor import extract_zip_to_review_folder
from review_engine.classifier import detect_project_type
from review_engine.rubric_loader import load_rubric
from review_engine.evaluator import evaluate_rubric
from review_engine.feedback_generator import generate_feedback_markdown
from review_engine.utils import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Review Agent MVP")
    parser.add_argument("--zip", required=True, help="Path to student project zip file")
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
    args = parse_args()
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

    evidence_path = review_dir / "evidence.json"
    write_json(evidence_path, evidence_output)

    feedback = generate_feedback_markdown(
        project_name=rubric["project_name"],
        detected=detected,
        evaluation=evaluation,
    )

    feedback_md = review_dir / "feedback.md"
    feedback_txt = review_dir / "feedback.txt"

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


if __name__ == "__main__":
    main()
