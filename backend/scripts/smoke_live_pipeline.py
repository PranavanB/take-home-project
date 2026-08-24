import io
import time

import httpx
from reportlab.pdfgen import canvas


def make_synthetic_cv() -> bytes:
    lines = [
        "Jordan Taylor",
        "London, United Kingdom",
        "Industry: Information",
        "Senior Software Engineer - Cedar Systems, January 2022 to Present",
        "Built reliable services and mentored engineers.",
        "Skills: Python; FastAPI; building RESTful web services;",
        "automated software delivery pipelines; monitoring application logs;",
        "communicating with business leaders; writing legal contracts.",
        "Education: BSc Computer Science, Northbridge University, 2018",
        "Qualification: AWS Certified Developer - Associate",
    ]
    output = io.BytesIO()
    document = canvas.Canvas(output)
    y = 780
    for line in lines:
        document.drawString(72, y, line)
        y -= 22
    document.save()
    return output.getvalue()


def main() -> None:
    base_url = "http://127.0.0.1:8015/api"
    with httpx.Client(timeout=30) as client:
        created = client.post(
            f"{base_url}/match-sessions",
            files={
                "resume": (
                    "synthetic-arctic-smoke.pdf",
                    make_synthetic_cv(),
                    "application/pdf",
                )
            },
        )
        created.raise_for_status()
        session = created.json()
        session_id = session["match_session_id"]
        started = time.monotonic()
        try:
            summary = session
            while summary["stage"] not in {"ready", "failed"}:
                if time.monotonic() - started > 360:
                    raise TimeoutError("Live pipeline did not finish within six minutes")
                time.sleep(2)
                summary_response = client.get(f"{base_url}/match-sessions/{session_id}")
                summary_response.raise_for_status()
                summary = summary_response.json()
                client.post(f"{base_url}/match-sessions/{session_id}/heartbeat").raise_for_status()

            if summary["stage"] != "ready":
                raise RuntimeError(f"Live pipeline failed: {summary['safe_error']}")

            profile_response = client.get(f"{base_url}/match-sessions/{session_id}/profile")
            profile_response.raise_for_status()
            results_response = client.get(f"{base_url}/match-sessions/{session_id}/results")
            results_response.raise_for_status()
            profile = profile_response.json()
            results = results_response.json()

            print(f"elapsed_seconds={time.monotonic() - started:.2f}")
            print(f"raw_skills={len(profile['skills'])}")
            print(f"standardized_skills={len(profile['standardized_skills'])}")
            for skill in profile["standardized_skills"]:
                print(
                    f"mapped={skill['preferred_label']} "
                    f"method={skill['mapping_method']} similarity={skill['similarity']}"
                )
            print(f"top_matches={len(results['top_matches'])}")
            for match in results["top_matches"]:
                print(
                    f"match={match['title']} required="
                    f"{match['required_met']}/{match['required_total']}"
                )
            print("live_arctic_pipeline=passed")
        finally:
            client.post(
                f"{base_url}/match-sessions/{session_id}/close",
                headers={"X-Job-Matcher-Close-Reason": "user-reset"},
            ).raise_for_status()


if __name__ == "__main__":
    main()
