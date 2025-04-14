from typing import Optional, Generator
from forgeserve.runners.base import BaseRunner, DeploymentStatus
from forgeserve.runners.kubernetes import KubernetesRunner
class StatusManager:
    """Handles fetching status and logs via the runner."""

    def __init__(self, runner: BaseRunner):
        self.runner = runner

    def get_status(self, name: str, namespace: str) -> Optional[DeploymentStatus]:
        """Gets deployment status using the runner."""
        try:
            common_labels = self.runner._get_common_labels(name)
            return self.runner.get_status(name, namespace, common_labels)
        except Exception as e:
            print(f"Error fetching status for '{name}': {e}")
            return None

    def get_logs(self, name: str, namespace: str, follow: bool = False, tail_lines: Optional[int] = None) -> Generator[str, None, None]:
        """Streams logs using the runner."""
        try:
            common_labels = self.runner._get_common_labels(name)
            yield from self.runner.get_logs(name, namespace, common_labels, follow, tail_lines)
        except Exception as e:
            print(f"Error streaming logs for '{name}': {e}")



    def list_deployments(self, namespace: str) -> list:
        """Lists deployments managed by ForgeServe in a namespace."""
        if isinstance(self.runner, KubernetesRunner):
            try:
                label_selector = "app.kubernetes.io/managed-by=forgeserve"
                deployments = self.runner.apps_v1_api.list_namespaced_deployment(
                    namespace, label_selector=label_selector
                )
                return [{"name": d.metadata.name, "namespace": d.metadata.namespace, "replicas": d.spec.replicas, "ready": d.status.ready_replicas if d.status else 0} for d in deployments.items]
            except Exception as e:
                 print(f"Error listing deployments in namespace {namespace}: {e}")
                 return []
        else:
             print("Warning: Listing deployments not implemented for the current runner.")
             return []