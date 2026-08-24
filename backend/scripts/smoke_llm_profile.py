"""Run one schema-constrained, grounded profile extraction against local vLLM."""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from uuid import uuid4, uuid5

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain import (  # noqa: E402
    CandidateProfile,
    DocumentType,
    ExtractedBlock,
    ExtractedDocument,
)
from app.gateway import VLLMProfileDraftGenerator  # noqa: E402
from app.profile_extractor import ProfileExtractor  # noqa: E402

MINIMUM_COUNTS = {
    "experiences": 2,
    "skills": 5,
    "qualifications": 1,
    "education": 1,
}


def make_synthetic_document() -> ExtractedDocument:
    text = (PROJECT_ROOT / "seed" / "sample-resume.md").read_text(encoding="utf-8")
    resume_id = uuid4()
    return ExtractedDocument(
        reader_version="synthetic-smoke-v1",
        resume_id=resume_id,
        document_type=DocumentType.PDF,
        page_count=1,
        char_count=len(text),
        blocks=[
            ExtractedBlock(
                block_id=uuid5(resume_id, "block:1"),
                ordinal=1,
                source_label="Synthetic sample",
                page_number=1,
                kind="page",
                text=text,
            )
        ],
    )


async def extract_once(
    base_url: str,
    model: str,
    timeout: float,
    enable_thinking: bool,
) -> tuple[float, CandidateProfile]:
    document = make_synthetic_document()
    generator = VLLMProfileDraftGenerator(
        base_url=base_url,
        model=model,
        timeout_seconds=timeout,
        enable_thinking=enable_thinking,
    )
    started = time.perf_counter()
    profile = await ProfileExtractor(generator).extract(document)
    elapsed = time.perf_counter() - started
    return elapsed, profile


async def run(
    base_url: str,
    model: str,
    timeout: float,
    concurrency: int,
    show_synthetic_profile: bool,
    enable_thinking: bool,
) -> None:
    results = await asyncio.gather(
        *(
            extract_once(base_url, model, timeout, enable_thinking)
            for _ in range(concurrency)
        )
    )

    # Print only metadata and counts: smoke-test logs must not contain CV content.
    print(f"concurrency={concurrency}")
    for index, (elapsed, profile) in enumerate(results, start=1):
        print(f"request_{index}_elapsed_seconds={elapsed:.2f}")
        print(f"request_{index}_profile_id={profile.profile_id}")
        print(f"request_{index}_experiences={len(profile.experiences)}")
        print(f"request_{index}_skills={len(profile.skills)}")
        print(f"request_{index}_qualifications={len(profile.qualifications)}")
        print(f"request_{index}_education={len(profile.education)}")
        if show_synthetic_profile:
            print(profile.model_dump_json(indent=2))

        actual_counts = {
            "experiences": len(profile.experiences),
            "skills": len(profile.skills),
            "qualifications": len(profile.qualifications),
            "education": len(profile.education),
        }
        below_minimum = [
            name
            for name, minimum in MINIMUM_COUNTS.items()
            if actual_counts[name] < minimum
        ]
        if below_minimum:
            raise RuntimeError(
                "Synthetic extraction missed required categories: "
                + ", ".join(below_minimum)
            )
    print("structured_profile_smoke=passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="job-matcher-llm")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--concurrency", type=int, choices=range(1, 3), default=1)
    parser.add_argument("--show-synthetic-profile", action="store_true")
    parser.add_argument("--enable-thinking", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        run(
            args.base_url,
            args.model,
            args.timeout,
            args.concurrency,
            args.show_synthetic_profile,
            args.enable_thinking,
        )
    )


if __name__ == "__main__":
    main()
