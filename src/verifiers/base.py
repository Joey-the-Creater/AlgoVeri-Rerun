"""Abstract base class for verifiers."""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseVerifier(ABC):
    @abstractmethod
    def verify(self, source: str, spec: str, **kwargs: Any) -> Dict[str, Any]:
        """Run the verifier on the given source and spec, returning a result dict.

        The result dictionary should contain at least:
            - `ok`: bool
            - `reason`: str (optional)
            - `raw`: provider-specific raw output (optional)
        """

    ...
