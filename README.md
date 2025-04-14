# ForgeServe 🔥

**ForgeServe: Declarative Deployment & Management for LLM Serving Frameworks (vLLM, Ollama) on Kubernetes.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![PyPI version](https://badge.fury.io/py/forgeserve.svg)](https://badge.fury.io/py/forgeserve) 
<!-- [![Build Status](https://github.com/YOUR_ORG/forgeserve/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/forgeserve/actions/workflows/ci.yml) -->
<!-- [![Docs](https://img.shields.io/badge/docs-passing-brightgreen)](https://your-docs-url.com) -->
<!-- [![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/YOUR_ORG/forgeserve/badge)](https://securityscorecards.dev/viewer/?uri=github.com/YOUR_ORG/forgeserve)  -->


ForgeServe radically simplifies deploying and managing popular Large Language Model (LLM) serving frameworks like **vLLM and Ollama** (with TGI planned) directly onto **Kubernetes**. Move from selecting your model to having a scalable, optimized inference endpoint running on K8s much faster.

Define *what* you want using simple **declarative configuration (`--config file.yaml`)** for full control, **or instantly deploy common models using just a model ID (`forgeserve launch <model_id>`)** for rapid testing and development. ForgeServe handles the *how* – translating your needs into optimized framework settings and generating best-practice Kubernetes manifests automatically.

Stop wrestling with complex Helm charts, obscure framework command-line flags, and verbose Kubernetes YAML. Start serving models efficiently.

---

## The Problem: LLM Serving Complexity

Deploying LLMs for inference often involves a steep learning curve and significant manual effort:

*   **Framework Labyrinth:** Choosing between frameworks like vLLM, Ollama, TGI, etc., each with unique strengths and configuration nuances.
*   **Flag Overload:** Deciphering and correctly setting numerous framework-specific flags or environment variables for performance tuning (e.g., Tensor Parallelism, quantization, sequence length, GPU memory utilization, specific images).
*   **Kubernetes Boilerplate:** Writing and maintaining non-trivial Kubernetes manifests for Deployments, Services, Persistent Volumes (for models), Autoscalers (HPAs), readiness/liveness probes, tolerations, and resource requests/limits.
*   **GPU Optimization:** Ensuring efficient allocation and utilization of expensive GPU resources within Kubernetes.
*   **Lifecycle Management:** Managing updates, rollbacks, logging, and status checking across distributed components.

## The Solution: ForgeServe

**ForgeServe abstracts this complexity.**

*   **For Full Control (Config File):** Define your desired state in a `forgeserve.yaml` file, specifying the model, framework adapter (`vllm`, `ollama`), resources (CPUs, memory, GPUs), desired image versions, persistent storage, custom tolerations, and framework-specific settings using structured keys.
*   **For Speed (Quick Launch):** Simply provide a Hugging Face model ID. ForgeServe uses sensible defaults (e.g., vLLM backend, 1 GPU, standard ports, auto-generated name) which you can override with command-line options.

ForgeServe then intelligently:

1.  **Translates:** Converts your high-level declarative configuration (from file or defaults+options) into the specific, optimized commands, environment variables, and settings required by the chosen serving framework.
2.  **Generates:** Creates tailored, best-practice Kubernetes manifest files (Deployment, Service, PVC configuration) based on your inputs, including probes, tolerations, and resource management.
3.  **Deploys:** Applies the generated manifests to your target Kubernetes cluster using your current `kubectl` context.
4.  **Manages:** Provides simple CLI/SDK commands to check status, view logs, and tear down deployments.

ForgeServe follows an **Open Core** model. Core functionality is open-source (Apache 2.0), while advanced features are planned for commercial licenses.

## Key Features 

*   **Declarative & Simple:** Define deployments with easy-to-read YAML for full control.
*   **Quick Launch:** Deploy standard models directly using their Hugging Face ID without writing a config file (`forgeserve launch <model_id>`).
*   **LLM Framework Abstraction:** Configure vLLM or Ollama via structured keys (e.g., `vllm_config.gpu_memory_utilization=0.85`) or rely on sensible defaults for quick launch.
*   **Optimized Kubernetes Native:** Automatically generates K8s Deployments and Services with best practices (probes, resource management, GPU tolerations, optional PVC mounting, lifecycle hooks like Ollama `postStart` model pull).
*   **Custom Images:** Specify exact container image versions for serving backends in your configuration file.
*   **Persistent Model Cache:** Optionally configure usage of a PersistentVolumeClaim (PVC) to cache downloaded models across pod restarts for both vLLM and Ollama.
*   **Dual Interface: CLI & Python SDK:** Manage deployments via a user-friendly command-line interface or integrate programmatically into MLOps workflows.
*   **Extensible Adapter System:** Designed to easily add support for new serving frameworks (TGI planned).
*   **Open Core:** Core Kubernetes deployment features are open-source (Apache 2.0). Advanced enterprise capabilities planned for commercial offering.

## Core Concepts Workflow

1.  **Define:**
    *   **Option A (Config File):** Create a `forgeserve.yaml` file detailing your deployment (`name`, `model`, `resources`, `backend`, `model_storage`, `tolerations`, etc.).
    *   **Option B (Quick Launch):** Identify the Hugging Face model ID and any desired overrides (GPUs, backend, namespace, etc.).
2.  **Launch:**
    *   **Option A:** Run `forgeserve launch --config <your_config.yaml>`.
    *   **Option B:** Run `forgeserve launch <model_id> [OPTIONS]`.
3.  **Translate & Generate:** ForgeServe parses the input (file or defaults+options), uses the appropriate adapter (`vllm`, `ollama`) to translate settings into framework commands/env vars, and generates Kubernetes manifest files (Deployment, Service).
4.  **Deploy:** ForgeServe applies the generated manifests to the Kubernetes cluster configured in your current `kubectl` context.
5.  **Manage:** Use commands like `forgeserve status <name>`, `forgeserve logs <name>`, and `forgeserve down <name>` (or SDK equivalents) to interact with the running deployment. The `<name>` might be auto-generated if using quick launch without `--name`.

## Getting Started 

**Prerequisites:**

*   Python 3.10+ (`uv` recommended for environment management)
*   `kubectl` installed and configured to access your target Kubernetes cluster.
*   Access to a Kubernetes cluster with GPU resources (if deploying GPU models).
*   *(Optional)* A provisioned PersistentVolumeClaim (PVC) in your target namespace if you want persistent model caching.

**1. Installation:**

```bash
# Create and activate a virtual environment (recommended)
# uv venv
# source .venv/bin/activate

# Install ForgeServe
pip install forgeserve
# Or install from source (after cloning): pip install .```
```
**2. Launching a Deployment (Choose ONE method):**

**Option A: Quick Launch (Recommended for trying out)**

Deploy a model directly using its Hugging Face ID. ForgeServe uses defaults (vLLM backend, 1 GPU, auto-generated name, etc.) unless overridden by options.

```bash
# Example 1: Deploy Qwen 1.5 0.5B Chat with defaults (vLLM, 1 GPU)
forgeserve launch Qwen/Qwen1.5-0.5B-Chat

# Example 2: Deploy Llama 3 with Ollama backend, 1 GPU, specific name/namespace
forgeserve launch llama3 --backend ollama --gpus 1 --name my-llama3-ollama -n ai-apps

# Example 3: Deploy Mistral 7B Instruct with vLLM, 2 GPUs (auto TP=2)
forgeserve launch mistralai/Mistral-7B-Instruct-v0.1 --gpus 2

# Deploy Qwen-1.5-0.5B using defaults (vLLM, 1 GPU)
forgeserve launch Qwen/Qwen1.5-0.5B-Chat
```
*   *After launching, note the auto-generated name (e.g., `qwen-qwen1-5-0-5b-chat-serving`)*
*   *Use this name in the commands below (replace `<deployment_name>`)*

*(See more Quick Launch examples under Usage)*

**Method B: Config File (Full Control)**

Create `my_deployment.yaml`:
```yaml
# my_deployment.yaml
name: my-custom-deployment
model: {source: huggingface, identifier: Qwen/Qwen1.5-0.5B-Chat}
resources: {requests: {nvidia.com/gpu: 1}, limits: {nvidia.com/gpu: 1}}
backend: {adapter: vllm}
```
Launch:
```bash
forgeserve launch --config my_deployment.yaml
```
*   *Use the name `my-custom-deployment` in the commands below*

*(See more Config File details under Usage)*

**3. Check Status:**

```bash
# Replace <deployment_name> with the actual name from step 2
# Replace <namespace> if you used -n or specified in YAML (default: default)
forgeserve status <deployment_name> -n <namespace>
```
*Output shows pod status and the Service endpoint (e.g., `10.x.x.x:8000`).*

**4. (Optional) Access Locally via Port-Forward:**

```bash
# Find service name (usually <deployment_name>-service)
kubectl get svc <deployment_name>-service -n <namespace>

# Forward local 8080 to the service port (e.g., 8000 for vLLM)
kubectl port-forward service/<deployment_name>-service -n <namespace> 8080:<service_port>
```
*Now access `http://localhost:8080`.*

**5. Send Inference Request:**

*(Example `curl` for vLLM OpenAI endpoint at `localhost:8080`)*
```bash
curl http://localhost:8080/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen/Qwen1.5-0.5B-Chat",
        "prompt": "Explain ForgeServe in one sentence",
        "max_tokens": 50
    }'
```

**6. View Logs:**

```bash
# Stream logs continuously
forgeserve logs <deployment_name> -n <namespace> --follow
```

**7. Tear Down:**

```bash
# Add --force or -y to skip confirmation
forgeserve down <deployment_name> -n <namespace>
```

## Usage Examples

### Launching Deployments

**1. Quick Launch (`forgeserve launch <MODEL_ID> [OPTIONS]`)**

*   **Simplest (vLLM, 1 GPU, default name/namespace):**
    ```bash
    forgeserve launch mistralai/Mistral-7B-Instruct-v0.1
    ```

*   **Ollama Backend (1 GPU, default name/namespace):**
    ```bash
    forgeserve launch llama3 --backend ollama
    ```

*   **Multiple GPUs (vLLM, auto TensorParallel):**
    ```bash
    forgeserve launch meta-llama/Llama-2-13b-chat-hf --gpus 2
    ```

*   **Custom Name and Namespace:**
    ```bash
    forgeserve launch NousResearch/Hermes-2-Pro-Llama-3-8B --name hermes-test -n ai-dev
    ```

*   **Adjust Resources:**
    ```bash
    forgeserve launch Qwen/Qwen1.5-1.8B-Chat --memory 16Gi --cpu 2
    ```

*   **Quick Launch Options Reference:**
    ```bash
    forgeserve launch --help
    ```
    *   `--backend TEXT`: `vllm` or `ollama` (default: `vllm`).
    *   `--gpus INTEGER`: Number of NVIDIA GPUs (default: `1`).
    *   `--name TEXT`: Set deployment name (default: auto-generated).
    *   `--port INTEGER`: Internal container port (defaults per backend).
    *   `--cpu TEXT`: CPU request (default: `"1"`).
    *   `--memory TEXT`: Memory request (default: `"4Gi"`).
    *   `--namespace TEXT`: Kubernetes namespace (default: `"default"`).

**2. Config File (`forgeserve launch --config <file.yaml>`)**

*   **Basic vLLM:**
    ```yaml
    # basic_vllm.yaml
    name: basic-vllm
    model: {source: huggingface, identifier: gpt2}
    resources: {requests: {nvidia.com/gpu: 1}, limits: {nvidia.com/gpu: 1}}
    backend: {adapter: vllm}
    ```
    ```bash
    forgeserve launch --config basic_vllm.yaml
    ```

*   **Ollama with PVC and Custom Image:**
    ```yaml
    # ollama_pvc.yaml
    name: ollama-cached
    namespace: llm-apps
    model: {source: huggingface, identifier: llama3}
    resources: {requests: {nvidia.com/gpu: 1}, limits: {nvidia.com/gpu: 1}}
    backend:
      adapter: ollama
      config:
        ollama_config:
          image: "ollama/ollama:0.1.32" # Pin version
          num_gpu: 1
    model_storage:
      pvc_name: my-llm-cache-pvc # Assumes PVC exists in llm-apps namespace
    tolerations:
      - {key: custom-taint, operator: Exists}
    ```
    ```bash
    forgeserve launch --config ollama_pvc.yaml
    ```

### Managing Deployments

*   **Check Status:**
    ```bash
    forgeserve status my-deployment-name
    forgeserve status my-deployment-name -n custom-namespace
    ```

*   **List Deployments:**
    ```bash
    forgeserve list
    forgeserve list -n ai-apps
    ```

*   **View Logs:**
    ```bash
    # Get recent logs
    forgeserve logs my-deployment-name -n my-namespace --tail 100

    # Stream new logs continuously
    forgeserve logs my-deployment-name -n my-namespace -f
    ```

*   **Delete Deployment:**
    ```bash
    # Will ask for confirmation
    forgeserve down my-deployment-name -n my-namespace

    # Skip confirmation
    forgeserve down my-other-deployment --force
    ```

## Configuration File Details

*(This section can remain largely the same as before, detailing the YAML fields: name, namespace, model, resources, backend (adapter, port, config (vllm_config, ollama_config(image), extra_args)), model_storage, tolerations)*

**(Link to detailed Configuration Reference in your documentation)**

See the `examples/` directory in the repository for more configuration examples.

<!-- ## Python SDK

*(Keep the SDK example as before, ensuring it uses the updated config models)*

```python
from forgeserve.sdk import ForgeClient
from forgeserve.config import (
    DeploymentConfig, ModelSource, ResourceSpec, ResourceRequests,
    BackendConfig, VLLMBackendAdapterConfig, OllamaConfig,
    ModelStorageConfig, Toleration
)

client = ForgeClient()
# ... (rest of SDK example) ...
``` -->

## Supported Backends & Platforms

*   **Serving Framework Adapters:** ✅ vLLM, ✅ Ollama, ⏳ TGI (Planned)
*   **Target Platform:** ✅ Kubernetes (K8s)

## Open Core Model

*(Keep this section as before)*

## Roadmap & Future Work

*   [ ] TGI Adapter
*   [ ] Advanced HPA Configuration
*   [ ] Monitoring Integration (Prometheus)
*   [ ] Ingress/Gateway Generation
*   [ ] Optional PVC Lifecycle Management
*   [ ] ForgeServe Enterprise Features
*   [ ] Enhanced Documentation