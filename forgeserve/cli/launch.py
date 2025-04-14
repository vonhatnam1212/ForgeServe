import typer
from pathlib import Path
from typing_extensions import Annotated
from typing import Optional
import re
import click
from rich.console import Console
from rich.syntax import Syntax
from forgeserve.config.models import (
    DeploymentConfig,
    ModelSource,
    ResourceSpec,
    ResourceRequests,
    BackendConfig,
    OllamaConfig,
    VLLMConfig,
    BackendAdapterConfig,
)
import yaml
from forgeserve.config.loaders import load_config_from_yaml
from forgeserve.runners.kubernetes import KubernetesRunner
from forgeserve.core.deployment_manager import DeploymentManager

console = Console()


def _sanitize_name(base_name: str) -> str:
    """Converts a model ID or other string into a DNS-compatible name."""
    sanitized = base_name.lower()
    sanitized = re.sub(r"[_\/]+", "-", sanitized)
    sanitized = re.sub(r"[^a-z0-9-]+", "", sanitized)
    sanitized = sanitized.strip("-")
    # Limit length (optional, K8s limit is 63 for service names etc)
    sanitized = sanitized[:50]
    if not sanitized:
        return "llm-deployment"
    return f"{sanitized}-serving"


def _generate_quick_launch_config(
    model_id: str,
    name: Optional[str],
    namespace: str,
    gpus: Optional[int],
    backend: str,
    port: int,
    cpu: str,
    memory: str,
) -> DeploymentConfig:
    """Generates a default DeploymentConfig for quick launch."""

    deployment_name = name or _sanitize_name(model_id)
    console.print(f"   Generating default configuration for model '{model_id}'...")
    console.print(f"   Deployment Name: {deployment_name}")
    console.print(f"   Namespace:       {namespace}")
    console.print(f"   Backend Adapter: {backend}")
    console.print(f"   GPU Count:       {gpus}")
    console.print(f"   CPU request:     {cpu}")
    console.print(f"   Memory request:  {memory}")

    model_source = ModelSource(source="huggingface", identifier=model_id)

    resource_requests = ResourceRequests(
        cpu=cpu,
        memory=memory,
        nvidia_gpu=gpus if gpus > 0 else None,
    )

    resource_limits = ResourceRequests(nvidia_gpu=gpus if gpus > 0 else None)
    resource_spec = ResourceSpec(
        requests=resource_requests.model_dump(exclude_none=True, by_alias=True),
        limits=resource_limits.model_dump(exclude_none=True, by_alias=True),
    )

    adapter_config = BackendAdapterConfig()

    if backend == "vllm":
        vllm_specific_config = {
            "dtype": "auto",
            "gpu_memory_utilization": 0.90,
            "trust_remote_code": True,
        }
        if gpus > 1:
            vllm_specific_config["tensor_parallel_size"] = gpus
            console.print(
                f"   vLLM Config:     Auto-setting tensor_parallel_size={gpus}"
            )

        adapter_config.vllm_config = VLLMConfig(**vllm_specific_config)
    elif backend == "ollama":
        ollama_specific_config = {"num_gpu": 1 if gpus > 0 else 0, "keep_alive": "-1"}
        console.print(
            f"   Ollama Config:   num_gpu={ollama_specific_config['num_gpu']}, keep_alive='{ollama_specific_config['keep_alive']}'"
        )
        adapter_config.ollama_config = OllamaConfig(**ollama_specific_config)
    else:
        raise ValueError(f"Unsupported backend '{backend}' for quick launch.")

    backend_conf = BackendConfig(
        adapter=backend,
        port=port,
        config=adapter_config.model_dump(exclude_none=True, by_alias=True),
    )

    config = DeploymentConfig(
        name=deployment_name,
        namespace=namespace,
        replicas=1,
        model=model_source,
        resources=resource_spec,
        backend=backend_conf,
    )

    try:
        config.model_dump()
    except Exception as e:
        console.print(f"[bold red]Error validating generated config:[/bold red] {e}")
        raise typer.Exit(code=1)

    return config


def launch_deployment(
    config_path: Annotated[
        Optional[Path],
        typer.Option(
            "--file",
            "-f",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Path to the forgeserve.yaml configuration file. Mutually exclusive with <MODEL_ID>.",
            show_default=False,
        ),
    ] = None,
    model_id_arg: Annotated[
        Optional[str],
        typer.Argument(
            metavar="MODEL_ID | OLLAMA_TAG",
            help="Model identifier for quick launch. Provide a Hugging Face repo ID (e.g., 'Qwen/Qwen1.5-0.5B-Chat') for --backend vllm/tgi, OR an Ollama model tag (e.g., 'llama3', 'mistral:7b') for --backend ollama. Use EITHER this OR --config.",  # Updated help text
            show_default=False,
        ),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option(
            "--name",
            "-N",
            help="Override auto-generated deployment name (quick launch only).",
        ),
    ] = None,
    gpus: Annotated[
        int,
        typer.Option("--gpus", help="Number of GPUs to request (quick launch only)."),
    ] = 1,
    backend: Annotated[
        str,
        typer.Option("--backend", help="Serving backend adapter (quick launch only)."),
    ] = "vllm",
    port: Annotated[
        Optional[int],
        typer.Option(
            "--port",
            help="Internal container port (defaults depend on backend: vLLM=8000, Ollama=11434).",
        ),
    ] = 8000,
    cpu: Annotated[
        str, typer.Option("--cpu", help="CPU request (e.g., '1') (quick launch only).")
    ] = "1",
    memory: Annotated[
        str,
        typer.Option(
            "--memory", help="Memory request (e.g., '4Gi') (quick launch only)."
        ),
    ] = "4Gi",
    namespace: Annotated[
        str,
        typer.Option(
            "--namespace",
            "-n",
            help="Kubernetes namespace for deployment (overrides config file value if set).",
        ),
    ] = "default",
):
    """
    Creates or updates an LLM deployment on Kubernetes.

    You must provide EITHER the --config option OR a MODEL_ID argument.
    \n
    Examples:
    \n
    *   Using config file:\n
        `forgeserve launch --config ./my_app.yaml`\n
        `forgeserve launch -c path/to/config.yaml -n production`\n
    \n
    *   Using quick launch with model ID:\n
        `forgeserve launch Qwen/Qwen1.5-0.5B-Chat`\n
        `forgeserve launch mistralai/Mistral-7B-v0.1 --gpus 2 --name my-mistral -n dev`\n
    \n
    *   Using quick launch (Ollama):\n
        `forgeserve launch mistral --backend ollama --namespace ai-apps`\n
        `forgeserve launch llama3:8b --backend ollama --gpus 1 --name my-llama3`\n
    """
    config: Optional[DeploymentConfig] = None
    is_quick_launch = False
    final_namespace = namespace
    port_default = (
        port if port is not None else (11434 if backend.lower() == "ollama" else 8000)
    )

    if config_path and model_id_arg:
        console.print(
            "[bold red]Error:[/bold red] Cannot use both --config option and MODEL_ID argument."
        )
        raise typer.Exit(code=1)
    if not config_path and not model_id_arg:
        console.print(
            "[bold red]Error:[/bold red] Must provide either --config option or a MODEL_ID argument."
        )
        raise typer.Exit(code=1)

    if config_path:
        is_quick_launch = False
        console.print(f"Loading configuration from file: {config_path}")

        quick_launch_opts_used = any(
            [
                name is not None,
                gpus != 1,
                backend != "vllm",
                port != 8000,
                cpu != "1",
                memory != "4Gi",
            ]
        )
        if quick_launch_opts_used:
            console.print(
                "[bold red]Error:[/bold red] Cannot use quick launch options (--name, --gpus, etc.) when using --config."
            )
            raise typer.Exit(code=1)

        try:
            config = load_config_from_yaml(config_path)

            ctx = click.get_current_context()
            if (
                ctx.get_parameter_source("namespace")
                == click.core.ParameterSource.COMMANDLINE
            ):
                config.namespace = namespace
                final_namespace = namespace
            else:
                final_namespace = config.namespace

        except Exception as e:
            raise typer.Exit(code=1)

    elif model_id_arg:
        is_quick_launch = True
        final_namespace = namespace
        console.print(f"Preparing quick launch for model ID: {model_id_arg}")
        try:
            config = _generate_quick_launch_config(
                model_id=model_id_arg,
                name=name,
                namespace=final_namespace,
                gpus=gpus,
                backend=backend.lower(),
                port=port_default,
                cpu=cpu,
                memory=memory,
            )
        except Exception as e:
            console.print(
                f"[bold red]Error generating quick launch config:[/bold red] {e}"
            )
            raise typer.Exit(code=1)

    if config:
        console.print(
            f"\nInitializing deployment for '{config.name}' in namespace '{final_namespace}'..."
        )

        try:
            runner = KubernetesRunner()
            manager = DeploymentManager(runner)
        except Exception as e:
            console.print(
                f"[bold red]Error initializing Kubernetes connection:[/bold red] {e}"
            )
            raise typer.Exit(code=1)

        try:
            manager.launch(config)
            console.print(
                f"\nSuccessfully initiated launch for deployment '{config.name}'."
            )
            console.print(
                f"Use 'forgeserve status {config.name} -n {final_namespace}' to check progress."
            )
            console.print(
                f"Use 'forgeserve logs {config.name} -n {final_namespace} -f' to stream logs."
            )
            svc_name = f"{config.name}-service"
            console.print(
                f"\nTo test locally (if service type is ClusterIP), you might use:"
            )
            console.print(
                f"   kubectl port-forward service/{svc_name} -n {final_namespace} LOCAL_PORT:{config.backend.port}"
            )

        except Exception as e:
            console.print(f"[bold red]Error during launch:[/bold red] {e}")
            raise typer.Exit(code=1)
    else:
        console.print(
            "[bold red]Internal Error: Configuration object not available.[/bold red]"
        )
        raise typer.Exit(code=1)
