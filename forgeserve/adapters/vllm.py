from typing import Dict, Any, Optional, List
from forgeserve.config.models import DeploymentConfig, VLLMConfig
from .base import BaseAdapter
from rich.console import Console

console = Console()
DEFAULT_VLLM_IMAGE = "vllm/vllm-openai:latest"


class VLLMAdapter(BaseAdapter):
    """Adapter for the vLLM serving framework."""

    @property
    def adapter_name(self) -> str:
        return "vllm"

    @property
    def vllm_config(self) -> VLLMConfig:
        return self.config.backend.config.vllm_config

    def get_container_spec(self) -> Dict[str, Any]:
        """Generates the K8s container spec for vLLM."""

        args = self._build_vllm_args()
        ports = [{"containerPort": self.config.backend.port, "name": "http"}]
        image = DEFAULT_VLLM_IMAGE
        env_vars = self._build_vllm_env()
        volume_mounts = self._get_volume_mounts()
        k8s_resources = self._get_resources()

        image_to_use = (
            self.vllm_config.image
            if self.vllm_config and self.vllm_config.image
            else DEFAULT_VLLM_IMAGE
        )
        console.print(f"[bold cyan]Info:[/] Using vLLM image: [green]{image_to_use}[/]")

        container_spec = {
            "name": f"{self.config.name}-container",
            "image": image,
            "args": args,
            "env": env_vars,
            "ports": ports,
            "volumeMounts": volume_mounts if volume_mounts else None,
            "resources": k8s_resources,
        }
        return container_spec

    def _build_vllm_args(self) -> List[str]:
        """Translates VLLMConfig into command line arguments."""
        args = ["--host", "0.0.0.0", "--port", str(self.config.backend.port)]

        args.extend(["--model", self.config.model.identifier])

        cfg = self.vllm_config
        if cfg.dtype:
            args.extend(["--dtype", cfg.dtype])
        if cfg.gpu_memory_utilization:
            args.extend(["--gpu-memory-utilization", str(cfg.gpu_memory_utilization)])
        if cfg.tensor_parallel_size:
            args.extend(["--tensor-parallel-size", str(cfg.tensor_parallel_size)])
        elif (
            self.config.resources.requests.nvidia_gpu
            and self.config.resources.requests.nvidia_gpu > 1
        ):
            args.extend(
                [
                    "--tensor-parallel-size",
                    str(self.config.resources.requests.nvidia_gpu),
                ]
            )
        if cfg.quantization:
            args.extend(["--quantization", cfg.quantization])
        if cfg.max_model_len:
            args.extend(["--max-model-len", str(cfg.max_model_len)])
        if cfg.trust_remote_code:
            args.append("--trust-remote-code")

        if cfg.extra_args:
            args.extend(cfg.extra_args)

        return args

    def get_readiness_probe(self) -> Optional[Dict[str, Any]]:
        """vLLM readiness probe (basic example checking /health)."""
        return self._get_common_probe_settings(
            path="/health",
            port=self.config.backend.port,
            initial_delay=180,
            period=20,
            failure=6,
        )

    def get_liveness_probe(self) -> Optional[Dict[str, Any]]:
        """vLLM liveness probe (basic example checking /health)."""
        return self._get_common_probe_settings(
            path="/health",
            port=self.config.backend.port,
            initial_delay=180,
            period=20,
            failure=5,
        )

    def _build_vllm_env(self) -> List[Dict[str, str]]:
        """Build environment variables for the vLLM container."""
        env = [
            {"name": "HF_HUB_ENABLE_HF_TRANSFER", "value": "1"},
        ]

        if self.config.model_storage and self.config.model_storage.pvc_name:

            hf_home_path = "/hf-cache"
            env.append({"name": "HF_HOME", "value": hf_home_path})

        return env

    def _get_volume_mounts(self) -> Optional[List[Dict[str, str]]]:
        """Get volume mounts, including shared memory and model cache."""
        mounts = [{"name": "dshm", "mountPath": "/dev/shm"}]

        if self.config.model_storage and self.config.model_storage.pvc_name:
            volume_name = "llm-models-storage"
            mount_path = self.config.model_storage.mount_path if self.config.model_storage.mount_path else "/hf-cache" 
            mounts.append({"name": volume_name, "mountPath": mount_path})
        return mounts

    def _get_resources(self) -> Dict[str, Any]:
        """Prepare Kubernetes resource dictionary (Helper)."""
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

    def get_volumes(self) -> Optional[List[Dict[str, Any]]]:
        """Define volumes needed, including shared memory and model cache PVC."""
        volumes = [
            {
                "name": "dshm",
                "emptyDir": {"medium": "Memory"},
            } 
        ]
        if self.config.model_storage and self.config.model_storage.pvc_name:
            volume_name = "llm-models-storage"
            volumes.append(
                {
                    "name": volume_name,
                    "persistentVolumeClaim": {
                        "claimName": self.config.model_storage.pvc_name
                    },
                }
            )
        return volumes if volumes else None
