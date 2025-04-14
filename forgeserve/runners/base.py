from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator
from pydantic import BaseModel

class DeploymentStatus(BaseModel):
    """Simple status model returned by runners."""
    name: str
    namespace: str
    desired_replicas: Optional[int] = None
    ready_replicas: int
    pods: List[Dict[str, Any]] 
    service_endpoint: Optional[str]
class BaseRunner(ABC):
    """Abstract Base Class for execution backends (Kubernetes, etc.)."""

    @abstractmethod
    def apply(self, manifests: List[Dict[str, Any]], namespace: str):
        """Apply (create or update) Kubernetes resources from manifests."""
        pass

    @abstractmethod
    def delete(self, name: str, namespace: str, labels: Dict[str, str]):
        """Delete resources associated with a deployment name/labels."""
        pass

    @abstractmethod
    def get_status(self, name: str, namespace: str, labels: Dict[str, str]) -> Optional[DeploymentStatus]:
        """Get the status of a deployment."""
        pass

    @abstractmethod
    def get_logs(self, name: str, namespace: str, labels: Dict[str, str], follow: bool = False, tail_lines: Optional[int] = None) -> Generator[str, None, None]:
        """Get logs from the pods of a deployment."""
        pass

    def _get_common_labels(self, deployment_name: str) -> Dict[str, str]:
         """Generate standard labels for ForgeServe managed resources."""
         return {
             "app.kubernetes.io/name": deployment_name,
             "app.kubernetes.io/managed-by": "forgeserve",
         }