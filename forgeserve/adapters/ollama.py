from typing import Dict, Any, Optional, List
from forgeserve.config.models import DeploymentConfig, OllamaConfig, ModelStorageConfig
from .base import BaseAdapter

DEFAULT_OLLAMA_IMAGE = "ollama/ollama:latest"

class OllamaAdapter(BaseAdapter):
    """Adapter for the Ollama serving framework."""

    @property
    def adapter_name(self) -> str:
        return "ollama"

    @property
    def ollama_config(self) -> OllamaConfig:
        return self.config.backend.config.ollama_config

    def get_container_spec(self) -> Dict[str, Any]:
        """Generates the K8s container spec for Ollama."""
        args = [] 
        ports = [{"containerPort": self.config.backend.port, "name": "http"}]
        image_to_use = (
            self.ollama_config.image
            if self.ollama_config and self.ollama_config.image
            else DEFAULT_OLLAMA_IMAGE
        )

        env_vars = self._build_ollama_env()
        volume_mounts = self._get_volume_mounts()
        k8s_resources = self._get_k8s_resources() 

        container_spec = {
            "name": f"{self.config.name}-container",
            "image": image_to_use,
            "args": args if args else None,
            "env": env_vars,
            "ports": ports,
            "volumeMounts": volume_mounts if volume_mounts else None,
            "resources": k8s_resources,
        }

        readiness_probe = self.get_readiness_probe()
        if readiness_probe:
            container_spec["readinessProbe"] = readiness_probe
        liveness_probe = self.get_liveness_probe()
        if liveness_probe:
            container_spec["livenessProbe"] = liveness_probe

        model_id = self.config.model.identifier
        pull_command = f"echo 'Pulling model {model_id} via postStart hook...' && ollama pull {model_id} && echo 'Model pull command finished for {model_id}'"
        container_spec["lifecycle"] = {
                "postStart": {
                    "exec": {
                        "command": [
                            "/bin/sh",
                            "-c",
                            pull_command
                        ]
                    }
                }
            }
        return container_spec

    def _build_ollama_env(self) -> List[Dict[str, str]]:
        """Build environment variables for the Ollama container."""
        env = []
        cfg = self.ollama_config
        backend_port = self.config.backend.port

        env.append({"name": "OLLAMA_HOST", "value": f"0.0.0.0:{backend_port}"})

        if cfg.num_gpu is not None:
             env.append({"name": "OLLAMA_NUM_GPU", "value": str(cfg.num_gpu)})
        if cfg.models_dir:
             env.append({"name": "OLLAMA_MODELS", "value": cfg.models_dir})
        if cfg.keep_alive:
             env.append({"name": "OLLAMA_KEEP_ALIVE", "value": cfg.keep_alive})

        env.append({"name": "HF_HUB_ENABLE_HF_TRANSFER", "value": "1"})

        return env

    def _get_volume_mounts(self) -> Optional[List[Dict[str, str]]]:
        """Get volume mounts, primarily for model storage."""
        mounts = []
        if self.config.model_storage and self.config.model_storage.pvc_name:
            mounts.append({
                "name": "ollama-models-storage", 
                "mountPath": self.config.model_storage.mount_path 
            })

        return mounts if mounts else None

    def _get_k8s_resources(self) -> Dict[str, Any]:
        """Prepare Kubernetes resource dictionary."""
        resources = {
            "requests": self.config.resources.requests.model_dump(
                exclude_none=True, by_alias=True
            ),
            "limits": {},
        }
        if self.config.resources.limits:
            resources["limits"] = self.config.resources.limits.model_dump(
                exclude_none=True, by_alias=True
            )

        resources = {k: v for k, v in resources.items() if v}
        return resources

    def get_readiness_probe(self) -> Optional[Dict[str, Any]]:
        """Ollama readiness probe (simple HTTP check)."""
        return self._get_common_probe_settings(
            path="/", 
            port=self.config.backend.port,
            initial_delay=180,
            period=10,
            failure=3
        )

    def get_liveness_probe(self) -> Optional[Dict[str, Any]]:
        """Ollama liveness probe."""
         # Can use the same check as readiness
        return self._get_common_probe_settings(
            path="/",
            port=self.config.backend.port,
            initial_delay=180,
            period=20,
            failure=3
        )

    def get_volumes(self) -> Optional[List[Dict[str, Any]]]:
        """Define volumes, primarily for model storage from PVC."""
        volumes = []
        if self.config.model_storage and self.config.model_storage.pvc_name:
            volumes.append({
                "name": "ollama-models-storage",
                "persistentVolumeClaim": {
                    "claimName": self.config.model_storage.pvc_name
                }
            })
        return volumes if volumes else None