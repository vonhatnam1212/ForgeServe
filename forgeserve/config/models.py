from typing import Optional, Dict, Any, Literal, List
from pydantic import BaseModel, Field, model_validator, field_validator

# --- Resource Related Models ---


class Toleration(BaseModel):
    """Represents a Kubernetes Toleration."""

    key: Optional[str] = None
    operator: Literal["Exists", "Equal"] = "Equal"
    value: Optional[str] = None
    effect: Optional[Literal["NoSchedule", "PreferNoSchedule", "NoExecute"]] = None
    tolerationSeconds: Optional[int] = Field(None, ge=0)

    @model_validator(mode="before")
    def check_value_for_equal_operator(cls, data: dict):
        if data.get("operator") == "Equal" and "value" in data:
            if data.get("key") is not None:
                raise ValueError(
                    "Toleration value is required when operator is 'Equal' and key is set."
                )
        if data.get("operator") == "Exists" and "value" in data:
            data["value"] = None
        return data

    @model_validator(mode="before")
    def check_effect_for_noexecute(cls, data: dict):
        if data.get("tolerationSeconds") and data.get("value"):
            if data.get("value") != "NoExecute":
                raise ValueError(
                    "tolerationSeconds can only be specified when effect is 'NoExecute'"
                )
        return data


class ResourceRequests(BaseModel):
    cpu: Optional[str] = Field(None, description="CPU request (e.g., '1', '500m')")
    memory: Optional[str] = Field(
        None, description="Memory request (e.g., '4Gi', '1024Mi')"
    )
    nvidia_gpu: Optional[int] = Field(
        default=None,
        alias="nvidia.com/gpu",
        ge=1,
        description="Number of NVIDIA GPUs requested (e.g., 1)",
    )

    class Config:
        allow_population_by_field_name = True


class ResourceSpec(BaseModel):
    requests: ResourceRequests = Field(
        ..., description="Resource requests for the container"
    )
    limits: Optional[ResourceRequests] = Field(
        None, description="Resource limits for the container"
    )

    @model_validator(mode="before")
    def check_limits_against_requests(cls, data: dict):

        if "limits" in data and "requests" in data and data["requests"]:
            requests_data = data["requests"]
            limits_data = data["limits"]

            req_gpu_count = requests_data.get("nvidia.com/gpu")
            lim_gpu_count = limits_data.get("nvidia.com/gpu")
            if (
                req_gpu_count is not None
                and lim_gpu_count is not None
                and req_gpu_count > lim_gpu_count
            ):
                raise ValueError(
                    "'nvidia.com/gpu' limits must be greater than or equal to requests"
                )

            req_cpu_val = requests_data.get("cpu")
            lim_cpu_val = limits_data.get("cpu")
            if (
                req_cpu_val is not None
                and lim_cpu_val is not None
                and req_cpu_val > lim_cpu_val
            ):
                raise ValueError(
                    f'CPU limits ({limits_data.get("cpu")}) must be greater than or equal to requests ({requests_data.get("cpu")})'
                )

            req_mem_val = requests_data.get("memory")
            lim_mem_val = limits_data.get("memory")
            if (
                req_mem_val is not None
                and lim_mem_val is not None
                and req_mem_val > lim_mem_val
            ):
                raise ValueError(
                    f'Memory limits ({limits_data.get("memory")}) must be greater than or equal to requests ({requests_data.get("memory")})'
                )
        return data


# --- Model Source ---


class ModelSource(BaseModel):
    source: Literal["huggingface", "s3", "local","ollama"] = Field(
        "huggingface", description="Source of the model"
    )
    identifier: str = Field(
        ..., description="Identifier (e.g., HF repo ID, S3 path, local path)"
    )


# --- Backend Adapters Config ---
# Define specific config structures for each adapter


class VLLMConfig(BaseModel):
    image: Optional[str] = Field(
        None,
        description="Override the default vLLM container image (e.g., 'vllm/vllm-openai:v0.4.1')."
    )
    dtype: Literal["auto", "half", "float16", "bfloat16", "float", "float32"] = "auto"
    gpu_memory_utilization: float = Field(0.9, ge=0.0, le=1.0)
    tensor_parallel_size: Optional[int] = Field(None, ge=1)
    quantization: Optional[Literal["awq", "gptq", "squeezellm"]] = None
    max_model_len: Optional[int] = None
    trust_remote_code: bool = True

    extra_args: List[str] = Field(
        default_factory=list,
        description="List of additional raw CLI arguments for vLLM",
    )


class TGIConfig(BaseModel):
    pass
    # quantize: Optional[Literal["bitsandbytes", "gptq", "awq"]] = None
    # max_total_tokens: int = 4096
    # max_input_length: Optional[int] = None
    # sharded: Optional[bool] = None # Auto-inferred based on replicas/resources?
    # num_shard: Optional[int] = None # Often same as tensor_parallel_size
    # trust_remote_code: bool = False
    # extra_env_vars: Dict[str, str] = Field(default_factory=dict, description="Additional environment variables for TGI")


class OllamaConfig(BaseModel):
    image: Optional[str] = Field(
        None,
        description="Override the default Ollama container image (e.g., 'ollama/ollama:0.1.32')."
    )
    num_gpu: Optional[int] = Field(
        None,
        ge=0,
        description="Number of GPU layers to offload (maps to OLLAMA_NUM_GPU). 0 for CPU only. Default lets Ollama decide.",
    )
    models_dir: Optional[str] = Field(
        None,
        description="Path inside the container where models are stored (maps to OLLAMA_MODELS).",
    )
    keep_alive: Optional[str] = Field(
        None,
        description="Duration models stay loaded in memory (maps to OLLAMA_KEEP_ALIVE).",
    )


class ModelStorageConfig(BaseModel):
    pvc_name: Optional[str] = Field(
        None,
        description="Name of an existing PersistentVolumeClaim to mount for model storage.",
    )
    mount_path: str = Field(
        None,
        description="Path inside the container where the PVC should be mounted.",
    )


class BackendAdapterConfig(BaseModel):
    vllm_config: Optional[VLLMConfig] = Field(None)
    tgi_config: Optional[TGIConfig] = Field(None)
    ollama_config: Optional[OllamaConfig] = Field(None)


class BackendConfig(BaseModel):
    adapter: Literal["vllm", "tgi", "ollama"] = Field(
        ..., description="The serving framework adapter to use"
    )
    port: int = Field(
        8000, ge=1025, le=65535, description="Internal container port to expose"
    )
    config: BackendAdapterConfig = Field(
        default_factory=BackendAdapterConfig,
        description="Adapter-specific configuration",
    )

    @model_validator(mode="after")
    def ensure_adapter_config_exists(self) -> "BackendConfig":
        if self.adapter == "vllm" and self.config.vllm_config is None:
            print(
                "Info: 'vllm_config' not found in input, initializing empty vLLM config."
            )
            self.config.vllm_config = VLLMConfig()
        elif self.adapter == "ollama" and self.config.ollama_config is None:
            print("Info: 'ollama_config' not found, initializing empty Ollama config.")
            self.config.ollama_config = OllamaConfig()

        active_configs = sum(
            1
            for cfg in [
                self.config.vllm_config,
                self.config.tgi_config,
                self.config.ollama_config,
            ]
            if cfg is not None
        )
        if active_configs > 1:
            raise ValueError(
                f"Multiple adapter configs found ({[k for k,v in self.config.model_dump().items() if v]}) but adapter is '{self.adapter}'"
            )

        return self


# --- Main Deployment Configuration ---


class DeploymentConfig(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
        description="Unique name for the deployment (must be DNS-compatible)",
    )
    replicas: int = Field(1, ge=1, description="Number of deployment replicas")
    namespace: str = Field("default", description="Kubernetes namespace for deployment")

    model: ModelSource
    resources: ResourceSpec
    backend: BackendConfig

    labels: Dict[str, str] = Field(
        default_factory=dict, description="Custom labels for K8s resources"
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="Custom annotations for K8s resources"
    )

    tolerations: List[Toleration] = Field(
        default_factory=list,
        description="List of custom Kubernetes tolerations to add to the pods",
    )
    model_storage: Optional[ModelStorageConfig] = Field(
        None,
        description="Configuration for persistent model storage (e.g., using a PVC). If omitted, models are ephemeral.",
    )

    class Config:
        allow_population_by_field_name = True
