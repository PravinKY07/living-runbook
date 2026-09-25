"""Run a safe, read-only watsonx.ai configuration preflight.

This command does not print credentials and does not perform network inference.
"""

from app.config import get_settings
from app.services.model_gateway import WatsonxProvider


def main() -> None:
    result = WatsonxProvider(get_settings()).preflight()
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
