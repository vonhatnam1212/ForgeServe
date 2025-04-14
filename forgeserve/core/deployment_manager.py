from typing import Dict, Type
from forgeserve.config.models import DeploymentConfig
from forgeserve.runners.base import BaseRunner
from forgeserve.adapters.base import BaseAdapter
from forgeserve.adapters.vllm import VLLMAdapter
from forgeserve.adapters.ollama import OllamaAdapter 
from .resource_generator import generate_manifests
from rich.console import Console
from rich.syntax import Syntax
console = Console()

ADAPTER_MAP: Dict[str, Type[BaseAdapter]] = {
    "vllm": VLLMAdapter,
    "ollama": OllamaAdapter,
}

class DeploymentManager:
    """Handles the orchestration of launching and tearing down deployments."""

    def __init__(self, runner: BaseRunner):
        self.runner = runner

    def _get_adapter(self, config: DeploymentConfig) -> BaseAdapter:
        """Instantiates the correct adapter based on the config."""
        adapter_name = config.backend.adapter
        adapter_class = ADAPTER_MAP.get(adapter_name)
        if not adapter_class:
            raise ValueError(f"Unsupported backend adapter: {adapter_name}. Available: {list(ADAPTER_MAP.keys())}")
        return adapter_class(config)

    def launch(self, config: DeploymentConfig):
        """Generates manifests and applies them using the runner."""
        console.print(f"Launching deployment '{config.name}' using adapter '{config.backend.adapter}'...")
        try:
            adapter = self._get_adapter(config)
            manifests = generate_manifests(config, adapter)
            # console.print(manifests)
            self.runner.apply(manifests, config.namespace, config.name, config.labels, config.annotations)
            console.print(f"Deployment '{config.name}' apply process initiated.")
        except Exception as e:
            console.print(f"[bold red]Error launching deployment [/bold red]'{config.name}': {e}")
            raise

    def down(self, name: str, namespace: str):
        """Tears down a deployment using the runner."""
        console.print(f"Requesting teardown for deployment '{name}' in namespace '{namespace}'...")
        try:
            common_labels = self.runner._get_common_labels(name)
            self.runner.delete(name, namespace, common_labels)
            console.print(f"Teardown initiated for '{name}'.")
        except Exception as e:
            console.print(f"[bold red]Error tearing down deployment [/bold red]'{name}': {e}")
            raise