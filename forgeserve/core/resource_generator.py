from typing import List, Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os
import yaml

from forgeserve.config.models import DeploymentConfig
from forgeserve.adapters.base import BaseAdapter
from rich.console import Console

console = Console()


def to_yaml_filter(value, indent=2, default_flow_style=False):
    """Converts a Python object to a YAML string."""
    return yaml.dump(value, indent=indent, default_flow_style=default_flow_style).strip()

template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
jinja_env = Environment(
    loader=FileSystemLoader(template_dir),
    autoescape=select_autoescape(['yaml', 'yml']),
    trim_blocks=True,
    lstrip_blocks=True
)


jinja_env.filters['to_yaml'] = to_yaml_filter

def _validate_container_args(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """
    Finds container specs in a manifest and ensures all 'args' are strings.
    Returns the updated manifest.
    """
    if not isinstance(manifest, dict) or manifest.get("kind") not in ["Deployment", "StatefulSet", "Pod"]:
        return manifest 

    try:
        containers = manifest.get('spec', {}).get('template', {}).get('spec', {}).get('containers')

        if isinstance(containers, list):
            for container in containers:
                if not isinstance(container, dict):
                    continue

                original_args = container.get('args')
                if isinstance(original_args, list):
                    new_args = []
                    for arg in original_args:
                        if not isinstance(arg, str):
                            new_args.append(str(arg))
                        else:
                            new_args.append(arg)
                    container['args'] = new_args
        manifest["container"] = container
    except Exception as e:
        print(f"Warning: Could not process container args for conversion in manifest {manifest.get('metadata', {}).get('name', 'unknown')}: {e}")

    return manifest

def _validate_container_envs(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures all env.value fields in containers are strings.
    Returns updated manifest.
    """
    if not isinstance(manifest, dict) or manifest.get("kind") not in ["Deployment", "StatefulSet", "Pod"]:
        return manifest

    try:
        containers = manifest.get('spec', {}).get('template', {}).get('spec', {}).get('containers')

        if isinstance(containers, list):
            for container in containers:
                if not isinstance(container, dict):
                    continue

                envs = container.get('env')
                if isinstance(envs, list):
                    for env_var in envs:
                        if isinstance(env_var, dict) and 'value' in env_var:
                            val = env_var['value']
                            if not isinstance(val, str) and val is not None:
                                env_var['value'] = str(val)
        
        manifest["container"] = container
    except Exception as e:
        print(f"Warning: Could not process env vars in manifest {manifest.get('metadata', {}).get('name', 'unknown')}: {e}")

    return manifest

def generate_manifests(config: DeploymentConfig, adapter: BaseAdapter) -> List[Dict[str, Any]]:
    """Generates Kubernetes manifest dictionaries using Jinja2 templates."""
    manifests = []

    context = {
        "config": config, 
        "deploymentName": config.name,
        "namespace": config.namespace,
        "replicas": config.replicas,
        "labels": {
             **config.labels,
             "app.kubernetes.io/component": "inference-server",
             "forgeserve.io/adapter": config.backend.adapter,
        },
        "annotations": config.annotations,
        "servicePort": config.backend.port,
        "container": adapter.get_container_spec(), 
        "readinessProbe": adapter.get_readiness_probe(),
        "livenessProbe": adapter.get_liveness_probe(),
        "volumes": adapter.get_volumes(), 
    }

    # Deployment Manifest
    try:
        deployment_template = jinja_env.get_template("deployment.yaml.j2")
        deployment_yaml = deployment_template.render(context)
        deployment_manifest_validate_args = _validate_container_args(yaml.safe_load(deployment_yaml))
        deployment_manifest= _validate_container_envs(deployment_manifest_validate_args)
        manifests.append(deployment_manifest)
    except Exception as e:
        console.print(
            f"[bold red]Error rendering Deployment template:[/bold red] {e}"
            )
        raise

    # Service Manifest
    try:
        service_template = jinja_env.get_template("service.yaml.j2")
        service_yaml = service_template.render(context)
        manifests.append(yaml.safe_load(service_yaml))
    except Exception as e:
        console.print(f"[bold red]Error rendering Service template:[/bold red] {e}")
        raise

    console.print(f"Generated {len(manifests)} manifests for {config.name}")
    return manifests