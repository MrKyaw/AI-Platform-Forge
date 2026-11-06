"""Exercise real local model identities, embeddings, and structured citation validation."""

import asyncio
import json

from forge.config import Settings
from forge.ollama import Ollama, validate_answer


async def main() -> None:
    provider = Ollama(Settings.load().ollama_url)
    try:
        async with asyncio.timeout(120):
            models = await provider.models()
            vector = (await provider.embed(["The launch code is cedar."]))[0]
            evidence = [{"id": "smoke:0", "text": "The launch code is cedar."}]
            raw = "".join(
                [
                    piece
                    async for piece in provider.generate(
                        "What is the launch code?",
                        evidence,
                    )
                ]
            )
            answer = validate_answer(raw, evidence)
            assert not answer.abstained and "cedar" in answer.answer.lower()
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "models": models,
                        "embedding_dimensions": len(vector),
                        "answer": answer.model_dump(),
                    },
                    indent=2,
                )
            )
    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
