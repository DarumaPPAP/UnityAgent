from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Context.Retrieval.Knowledge.answer_generation import (
    AnswerRequest,
    DeterministicAnswerModel,
    KnowledgeAnswerGenerator,
    OpenAICompatibleAnswerModel,
)
from Context.Retrieval.Knowledge.knowledge_client import KnowledgeClientOptions, KnowledgeHttpClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Run grounded Knowledge Retrieval + answer generation")
    parser.add_argument("question")
    parser.add_argument("--base-url", default=os.environ.get("KNOWLEDGE_SERVICE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--token-env", default="KNOWLEDGE_SERVICE_TOKEN", help="Environment variable containing the bearer token")
    parser.add_argument("--profile", default="hybrid_v1")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--max-context-characters", type=int, default=12000)
    parser.add_argument("--correlation-id", default=os.environ.get("KNOWLEDGE_CORRELATION_ID"))
    parser.add_argument("--deterministic-model", action="store_true")
    args = parser.parse_args()

    token = os.environ.get(args.token_env, "").strip()
    if not token:
        parser.error(f"the bearer token must be supplied through {args.token_env}; it is never accepted as a CLI argument")

    if args.deterministic_model:
        model = DeterministicAnswerModel()
    else:
        model = OpenAICompatibleAnswerModel.from_environment()
    client = KnowledgeHttpClient(
        KnowledgeClientOptions(
            args.base_url,
            bearer_token=token,
            timeout_seconds=float(os.environ.get("KNOWLEDGE_CLIENT_TIMEOUT_SECONDS", "10")),
            max_retries=int(os.environ.get("KNOWLEDGE_CLIENT_MAX_RETRIES", "1")),
        )
    )
    result = KnowledgeAnswerGenerator(client, model).generate(
        AnswerRequest(
            question=args.question,
            top_k=args.top_k,
            retrieval_profile=args.profile,
            max_context_characters=args.max_context_characters,
            correlation_id=args.correlation_id,
        )
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status == "answered" else 2


if __name__ == "__main__":
    raise SystemExit(main())
