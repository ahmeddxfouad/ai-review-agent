from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

LLM_MODES = {"llm_assisted", "full_review"}
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
GEMINI_GENERATE_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_EVIDENCE_CHARS = 60_000
MAX_FEEDBACK_CHARS = 30_000


def is_llm_mode(review_mode: str) -> bool:
    return review_mode in LLM_MODES


def selected_llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "gemini").strip().lower()


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "\n\n[TRUNCATED]"


def _compact_check(check: dict[str, Any]) -> dict[str, Any]:
    evidence = check.get("evidence")
    if isinstance(evidence, dict):
        evidence = {
            key: evidence[key]
            for key in [
                "file",
                "folder",
                "matched",
                "missing",
                "matches",
                "total_matches",
                "matches_by_keyword",
                "matches_by_pattern",
                "command",
                "cwd",
                "exit_code",
                "expected_exit_code",
                "stdout",
                "stderr",
                "snippets",
            ]
            if key in evidence
        }

        for stream_key in ["stdout", "stderr"]:
            if isinstance(evidence.get(stream_key), str):
                evidence[stream_key] = _truncate(evidence[stream_key], 2_000)

        if isinstance(evidence.get("snippets"), list):
            evidence["snippets"] = evidence["snippets"][:5]

    return {
        "id": check.get("id"),
        "type": check.get("type"),
        "description": check.get("description"),
        "passed": check.get("passed"),
        "message": check.get("message"),
        "review_method": check.get("review_method"),
        "runtime_status": check.get("runtime_status"),
        "evidence": evidence,
    }


def _compact_evidence(evidence_output: dict[str, Any]) -> dict[str, Any]:
    evaluation = evidence_output.get("evaluation", {})
    compact_sections = []

    for section in evaluation.get("sections", []):
        compact_sections.append(
            {
                "id": section.get("id"),
                "title": section.get("title"),
                "requirement": section.get("requirement"),
                "status": section.get("status"),
                "pass_rule": section.get("pass_rule"),
                "review_method": section.get("review_method"),
                "runtime_status": section.get("runtime_status"),
                "skip_reason": section.get("skip_reason"),
                "checks": [
                    _compact_check(check)
                    for check in section.get("checks", [])
                ],
            }
        )

    return {
        "review_mode": evidence_output.get("review_mode"),
        "detected": evidence_output.get("detected"),
        "summary": evaluation.get("summary"),
        "sections": compact_sections,
    }


def _extract_response_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    text_parts = []
    for output_item in response.get("output", []):
        for content_item in output_item.get("content", []):
            if content_item.get("type") in {"output_text", "text"}:
                text = content_item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)

    return "\n".join(text_parts).strip()


def _extract_gemini_text(response: dict[str, Any]) -> str:
    text_parts = []
    for candidate in response.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)

    return "\n".join(text_parts).strip()


def _build_prompt(
    *,
    project_name: str,
    evidence_output: dict[str, Any],
    deterministic_feedback: str,
) -> str:
    compact_evidence = _compact_evidence(evidence_output)
    evidence_json = json.dumps(compact_evidence, indent=2, ensure_ascii=False)
    evidence_json = _truncate(evidence_json, MAX_EVIDENCE_CHARS)
    deterministic_feedback = _truncate(deterministic_feedback, MAX_FEEDBACK_CHARS)

    return f"""
Project rubric: {project_name}

You are helping a human reviewer draft final project review feedback.

Rules:
- Use only the evidence JSON and deterministic draft below.
- Do not claim that tests, builds, servers, migrations, or installs ran unless runtime evidence says they ran.
- Separate static evidence from runtime evidence.
- Preserve the rubric's pass/fail status for each section unless the evidence clearly says the deterministic draft is internally inconsistent.
- If evidence is missing or uncertain, say so clearly.
- Keep feedback personalized, accurate, clear, and thorough.
- Use Markdown.
- Keep the same broad structure: review summary, per-section feedback, recommendations, and final reviewer reminder.
- Do not invent file paths, commands, outputs, routes, tests, dependencies, or runtime results.

Evidence JSON:
```json
{evidence_json}
```

Deterministic draft feedback:
```markdown
{deterministic_feedback}
```
""".strip()


def _generate_openai_feedback(
    *,
    project_name: str,
    evidence_output: dict[str, Any],
    deterministic_feedback: str,
) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "status": "skipped",
            "reason": "OPENAI_API_KEY is not set.",
            "model": None,
            "provider": "openai",
            "feedback": deterministic_feedback,
        }

    model = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    prompt = _build_prompt(
        project_name=project_name,
        evidence_output=evidence_output,
        deterministic_feedback=deterministic_feedback,
    )

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are an evidence-grounded project review assistant. "
                    "You improve review feedback without inventing facts."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_output_tokens": 6000,
    }

    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "failed",
            "reason": f"OpenAI API HTTP {exc.code}: {_truncate(body, 1000)}",
            "model": model,
            "provider": "openai",
            "feedback": deterministic_feedback,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"OpenAI API request failed: {exc}",
            "model": model,
            "provider": "openai",
            "feedback": deterministic_feedback,
        }

    feedback = _extract_response_text(response_data)
    if not feedback:
        return {
            "status": "failed",
            "reason": "OpenAI API response did not contain output text.",
            "model": model,
            "provider": "openai",
            "feedback": deterministic_feedback,
        }

    return {
        "status": "completed",
        "reason": None,
        "model": model,
        "provider": "openai",
        "response_id": response_data.get("id"),
        "feedback": feedback,
    }


def _generate_gemini_feedback(
    *,
    project_name: str,
    evidence_output: dict[str, Any],
    deterministic_feedback: str,
) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {
            "status": "skipped",
            "reason": "GEMINI_API_KEY is not set.",
            "model": None,
            "provider": "gemini",
            "feedback": deterministic_feedback,
        }

    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    prompt = _build_prompt(
        project_name=project_name,
        evidence_output=evidence_output,
        deterministic_feedback=deterministic_feedback,
    )

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "You are an evidence-grounded project review assistant. "
                        "You improve review feedback without inventing facts."
                    )
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt,
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 6000,
        },
    }

    url = GEMINI_GENERATE_URL_TEMPLATE.format(model=model)
    request = urllib.request.Request(
        f"{url}?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "failed",
            "reason": f"Gemini API HTTP {exc.code}: {_truncate(body, 1000)}",
            "model": model,
            "provider": "gemini",
            "feedback": deterministic_feedback,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"Gemini API request failed: {exc}",
            "model": model,
            "provider": "gemini",
            "feedback": deterministic_feedback,
        }

    feedback = _extract_gemini_text(response_data)
    if not feedback:
        return {
            "status": "failed",
            "reason": "Gemini API response did not contain output text.",
            "model": model,
            "provider": "gemini",
            "feedback": deterministic_feedback,
        }

    return {
        "status": "completed",
        "reason": None,
        "model": model,
        "provider": "gemini",
        "response_id": None,
        "feedback": feedback,
    }


def list_gemini_models() -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {
            "status": "failed",
            "reason": "GEMINI_API_KEY is not set.",
            "models": [],
        }

    request = urllib.request.Request(
        f"{GEMINI_MODELS_URL}?key={api_key}",
        headers={"Content-Type": "application/json"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "failed",
            "reason": f"Gemini API HTTP {exc.code}: {_truncate(body, 1000)}",
            "models": [],
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"Gemini API request failed: {exc}",
            "models": [],
        }

    models = []
    for model in response_data.get("models", []):
        name = model.get("name", "")
        model_id = name.removeprefix("models/")
        methods = model.get("supportedGenerationMethods", [])
        models.append(
            {
                "name": name,
                "model_id": model_id,
                "display_name": model.get("displayName"),
                "supported_generation_methods": methods,
                "supports_generate_content": "generateContent" in methods,
            }
        )

    return {
        "status": "completed",
        "reason": None,
        "models": models,
    }


def generate_llm_feedback(
    *,
    project_name: str,
    evidence_output: dict[str, Any],
    deterministic_feedback: str,
) -> dict[str, Any]:
    provider = selected_llm_provider()

    if provider == "none":
        return {
            "status": "skipped",
            "reason": "LLM_PROVIDER is set to none.",
            "model": None,
            "provider": "none",
            "feedback": deterministic_feedback,
        }

    if provider == "gemini":
        return _generate_gemini_feedback(
            project_name=project_name,
            evidence_output=evidence_output,
            deterministic_feedback=deterministic_feedback,
        )

    if provider == "openai":
        return _generate_openai_feedback(
            project_name=project_name,
            evidence_output=evidence_output,
            deterministic_feedback=deterministic_feedback,
        )

    return {
        "status": "failed",
        "reason": f"Unsupported LLM_PROVIDER `{provider}`. Use openai, gemini, or none.",
        "model": None,
        "provider": provider,
        "feedback": deterministic_feedback,
    }
