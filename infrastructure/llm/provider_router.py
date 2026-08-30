"""ProviderRouter supporting fallback and concurrent multi-provider execution.

Not used by AllyCore/Scribe/Ally in this pass -- exists as a tested, working seam
for planned fallback and A/B testing features.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from infrastructure.llm.base_provider import LLMProvider, RetryableProviderMixin
from infrastructure.logger import log


class ProviderRouter:
    """Routes LLM provider calls with fallback and concurrent execution capabilities."""

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("ProviderRouter requires at least one provider.")
        self.providers = providers

    def call_with_fallback(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Tries providers[0], falls through to providers[1:] on any exception."""
        last_exception = None
        for i, provider in enumerate(self.providers):
            method = getattr(provider, method_name, None)
            if not callable(method):
                raise AttributeError(f"Provider {type(provider).__name__} has no method '{method_name}'")
            try:
                return method(*args, **kwargs)
            except Exception as e:
                last_exception = e
                log("Provider [{i}] ({name}) method '{method}' failed with {e}. Falling through...", i=i, name=type(provider).__name__, method=method_name, e=e)
                if i == len(self.providers) - 1:
                    raise
        if last_exception:
            raise last_exception
        raise RuntimeError("All providers failed without exception.")

    def call_concurrent(self, method_name: str, *args: Any, **kwargs: Any) -> dict[int, Any]:
        """Runs the same call against every provider concurrently, returning {provider_index: result_or_exception}."""
        results: dict[int, Any] = {}

        def _invoke(idx: int, prov: LLMProvider) -> tuple[int, Any]:
            try:
                method = getattr(prov, method_name)
                return idx, method(*args, **kwargs)
            except Exception as e:
                return idx, e

        with ThreadPoolExecutor(max_workers=len(self.providers)) as executor:
            futures = [executor.submit(_invoke, idx, prov) for idx, prov in enumerate(self.providers)]
            for future in as_completed(futures):
                idx, res = future.result()
                results[idx] = res

        return results
