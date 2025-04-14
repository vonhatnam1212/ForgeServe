from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from forgeserve.config.models import DeploymentConfig
# Import kubernetes client models only if needed for type hints, avoid heavy deps here
# from kubernetes.client import V1Container, V1Probe, V1VolumeMount, V1Volume

class BaseAdapter(ABC):
    """Abstract Base Class for LLM serving framework adapters."""

    def __init__(self, config: DeploymentConfig):
        self.config = config
        self._validate_config() 

    def _validate_config(self):
        """Check if the adapter-specific config part is present."""
        if self.config.backend.adapter != self.adapter_name:
             raise ValueError(f"Adapter '{self.adapter_name}' initialized with config for '{self.config.backend.adapter}'")
        if not getattr(self.config.backend.config, f"{self.adapter_name}_config", None):
             raise ValueError(f"Missing '{self.adapter_name}_config' in backend config for adapter '{self.adapter_name}'")


    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Return the name of the adapter (e.g., 'vllm')."""
        pass

    @abstractmethod
    def get_container_spec(self) -> Dict[str, Any]:
        """
        Generates the Kubernetes container specification dictionary elements.

        Should return a dictionary containing keys like:
        - image: str
        - command: Optional[List[str]]
        - args: Optional[List[str]]
        - env: Optional[List[Dict[str, Any]]] (e.g., [{'name': 'VAR', 'value': 'val'}])
        - ports: Optional[List[Dict[str, Any]]] (e.g., [{'containerPort': 8000}])
        - volumeMounts: Optional[List[Dict[str, Any]]]
        - resources: Dict[str, Any] (requests/limits from config)
        """
        pass

    @abstractmethod
    def get_readiness_probe(self) -> Optional[Dict[str, Any]]:
        """
        Generates the Kubernetes readiness probe specification dictionary.
        Returns None if no specific probe is recommended.
        """
        pass

    @abstractmethod
    def get_liveness_probe(self) -> Optional[Dict[str, Any]]:
        """
        Generates the Kubernetes liveness probe specification dictionary.
        Returns None if no specific probe is recommended.
        """
        pass

    def get_volumes(self) -> Optional[List[Dict[str, Any]]]:
        """
        Generates Kubernetes volume definitions needed by this adapter (e.g., for models).
        Default is no specific volumes required by the adapter itself.
        """
        return None

    def _get_common_probe_settings(self, path: str, port: int, initial_delay: int = 60, period: int = 15, failure: int = 5) -> Dict[str, Any]:
        """Helper to create common HTTP probe settings."""
        return {
            "httpGet": {
                "path": path,
                "port": port,
                "scheme": "HTTP"
            },
            "initialDelaySeconds": initial_delay,
            "periodSeconds": period,
            "timeoutSeconds": 5,
            "successThreshold": 1,
            "failureThreshold": failure,
        }