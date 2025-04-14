from typing import Optional, Dict, Any, Generator, Union, List
from pathlib import Path

from forgeserve.config.models import DeploymentConfig
from forgeserve.config.loaders import load_config_from_yaml, load_config_from_dict
from forgeserve.runners.base import BaseRunner, DeploymentStatus
from forgeserve.runners.kubernetes import KubernetesRunner # Default runner
from forgeserve.core.deployment_manager import DeploymentManager
from forgeserve.core.status_manager import StatusManager
from .exceptions import ForgeSdkException

class ForgeClient:
    """
    Python SDK Client for interacting with ForgeServe deployments.
    """

    def __init__(self, runner: Optional[BaseRunner] = None):
        """
        Initializes the client.

        Args:
            runner: An optional runner instance. Defaults to KubernetesRunner.
        """
        self.runner = runner or KubernetesRunner()
        # TODO: Consider how runner selection/configuration might work (e.g., env vars, params)
        self.deployment_manager = DeploymentManager(self.runner)
        self.status_manager = StatusManager(self.runner)
        print("ForgeClient initialized.")

    def launch(self, config: Union[DeploymentConfig, Dict[str, Any], Path, str]) -> Dict[str, Any]:
        """
        Launches or updates a deployment based on the provided configuration.

        Args:
            config: Deployment configuration as a DeploymentConfig object,
                    a dictionary, a path to a YAML file (str or Path).

        Returns:
            A dictionary indicating the action status (e.g., {"status": "launched", "name": name}).

        Raises:
            ForgeSdkException: If configuration loading or deployment fails.
        """
        try:
            if isinstance(config, DeploymentConfig):
                deployment_config = config
            elif isinstance(config, dict):
                deployment_config = load_config_from_dict(config)
            elif isinstance(config, (str, Path)):
                deployment_config = load_config_from_yaml(Path(config))
            else:
                raise TypeError("Invalid config type. Must be DeploymentConfig, dict, str, or Path.")

            self.deployment_manager.launch(deployment_config)
            return {"status": "launched", "name": deployment_config.name, "namespace": deployment_config.namespace}

        except Exception as e:
            # Wrap internal exceptions in SDK-specific exception
            raise ForgeSdkException(f"Failed to launch deployment: {e}") from e

    def down(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """
        Tears down (deletes) a ForgeServe deployment.

        Args:
            name: The name of the deployment.
            namespace: The Kubernetes namespace of the deployment.

        Returns:
            A dictionary indicating the action status (e.g., {"status": "teardown_initiated", "name": name}).

        Raises:
            ForgeSdkException: If teardown fails.
        """
        try:
            self.deployment_manager.down(name, namespace)
            return {"status": "teardown_initiated", "name": name, "namespace": namespace}
        except Exception as e:
            raise ForgeSdkException(f"Failed to tear down deployment '{name}': {e}") from e

    def status(self, name: str, namespace: str = "default") -> Optional[DeploymentStatus]:
        """
        Gets the status of a specific deployment.

        Args:
            name: The name of the deployment.
            namespace: The Kubernetes namespace of the deployment.

        Returns:
            A DeploymentStatus object containing status details, or None if not found/error.
        """
        try:
            return self.status_manager.get_status(name, namespace)
        except Exception as e:
            print(f"Error fetching status for '{name}': {e}") # Log error, but return None as per signature
            return None


    def logs(self, name: str, namespace: str = "default", follow: bool = False, tail_lines: Optional[int] = None) -> Generator[str, None, None]:
        """
        Streams or retrieves logs for a deployment.

        Args:
            name: The name of the deployment.
            namespace: The Kubernetes namespace of the deployment.
            follow: Whether to stream logs continuously (like `kubectl logs -f`).
            tail_lines: Number of lines from the end of the logs to show.

        Yields:
            Log lines as strings.

        Raises:
            ForgeSdkException: If fetching logs fails.
        """
        try:
            yield from self.status_manager.stream_logs(name, namespace, follow, tail_lines)
        except Exception as e:
            # Let the generator stop, but wrap the exception for clarity if needed downstream
            # Or simply let the original exception propagate if preferred.
             raise ForgeSdkException(f"Failed to stream logs for '{name}': {e}") from e


    def list(self, namespace: str = "default") -> List[Dict[str, Any]]:
        """
        Lists deployments managed by ForgeServe in a given namespace.

        Args:
            namespace: The Kubernetes namespace to list deployments in.

        Returns:
            A list of dictionaries, each representing a deployment summary.
        """
        try:
            return self.status_manager.list_deployments(namespace)
        except Exception as e:
            raise ForgeSdkException(f"Failed to list deployments in namespace '{namespace}': {e}") from e