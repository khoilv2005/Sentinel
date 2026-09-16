"""Method-neutral remote collector worker entrypoint.

The v0.3 implementation module remains `agentless_worker` temporarily so
existing imports and integration tests keep working during the v0.4 migration.
Operators and Compose use the product-neutral `collector-worker` name.
"""

from .agentless_worker import loop


if __name__ == "__main__":
    loop()
