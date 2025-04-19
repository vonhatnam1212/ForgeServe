# forgeserve/cli/benchmark.py

import typer
from typing_extensions import Annotated
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
import time
import asyncio
import sys
import uuid
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.spinner import Spinner
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from jinja2 import Environment, FileSystemLoader
import os
import yaml

from forgeserve.runners.kubernetes import KubernetesRunner 
from forgeserve.core.status_manager import StatusManager

from forgeserve.benchmark.metrics import BenchmarkStats, RequestResult

console = Console()


template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
try:
    jinja_env = Environment(loader=FileSystemLoader(template_dir), autoescape=False) # No HTML autoescape
    job_template = jinja_env.get_template("job.yaml.j2")
except Exception as e:
     console.print(f"[bold red]Error loading Job template:[/bold red] {e}")
     job_template = None 

def _get_k8s_clients():
    """Loads K8s config and returns API clients."""
    try:
        config.load_kube_config() 
        core_v1 = client.CoreV1Api()
        batch_v1 = client.BatchV1Api()
        apps_v1 = client.AppsV1Api() 
        return core_v1, batch_v1, apps_v1
    except Exception as e:
        console.print(f"[bold red]Error connecting to Kubernetes:[/bold red] {e}")
        console.print("   Ensure kubectl is configured correctly.")
        raise typer.Exit(code=1)


def _find_internal_service_endpoint(apps_v1: client.AppsV1Api, core_v1: client.CoreV1Api, deployment_name: str, namespace: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Finds internal service endpoint and model identifier."""
    service_name = f"{deployment_name}-service"
    model_identifier = None
    endpoint_url = None
    try:

        service = core_v1.read_namespaced_service(service_name, namespace)
        if not service.spec.ports or not service.spec.cluster_ip:
             console.print(f"[yellow]Warning:[/yellow] Service '{service_name}' found but missing ports or ClusterIP.")
             return None, None, None

        service_port = service.spec.ports[0].port

        endpoint_url = f"http://{service_name}.{namespace}.svc.cluster.local:{service_port}"

        try:
            deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
            model_identifier = deployment.metadata.labels.get("forgeserve.io/model-identifier")
        except ApiException as e:
             if e.status != 404: 
                  console.print(f"[yellow]Warning:[/yellow] Could not read Deployment '{deployment_name}' to get model label: {e.reason}")
        except Exception as e:
             console.print(f"[yellow]Warning:[/yellow] Error reading Deployment for model label: {e}")

        if not model_identifier:
            model_identifier = deployment_name
            console.print(f"[yellow]Warning:[/yellow] Using deployment name '{deployment_name}' as model identifier for API calls.")

        return endpoint_url, model_identifier, service_name

    except ApiException as e:
        if e.status == 404:
            console.print(f"[bold red]Error:[/bold red] Service '{service_name}' not found in namespace '{namespace}'.")
        else:
            console.print(f"[bold red]Error reading service '{service_name}':[/bold red] {e.reason}")
        return None, None, None
    except Exception as e:
        console.print(f"[bold red]Error finding service endpoint:[/bold red] {e}")
        return None, None, None

def _parse_duration(duration_str: str) -> Optional[int]:
    """Parses duration string (e.g., 30s, 2m, 1h) into seconds."""
    try:
        unit = duration_str[-1].lower()
        value = int(duration_str[:-1])
        if unit == 's': return value
        if unit == 'm': return value * 60
        if unit == 'h': return value * 3600
        raise ValueError("Invalid duration unit (use s, m, h)")
    except Exception as e:
        console.print(f"[bold red]Error parsing duration '{duration_str}':[/bold red] {e}")
        return None

def _wait_for_job_completion(batch_v1: client.BatchV1Api, namespace: str, job_name: str, timeout_seconds: int = 300) -> bool:
    """Polls the Job status until completion or timeout."""
    console.print(f"⏳ Waiting for benchmark Job '{job_name}' to complete (timeout: {timeout_seconds}s)...")
    start_time = time.monotonic()
    spinner = Spinner("dots", text=f" Waiting for Job '{job_name}'...")
    with console.status(spinner):
        while time.monotonic() - start_time < timeout_seconds:
            try:
                job_status = batch_v1.read_namespaced_job_status(job_name, namespace)
                status = job_status.status
                if status.succeeded and status.succeeded >= 1:
                    console.print(f"[green]Benchmark Job '{job_name}' succeeded.[/green]")
                    return True
                if status.failed and status.failed >= 1:

                    failed_count = status.failed
                    console.print(f"[bold red]Benchmark Job '{job_name}' failed ({failed_count} attempts).[/bold red]")

                    return False 

                active_pods = status.active if status.active else 0
                spinner.update(text=f" Waiting for Job '{job_name}' (Active Pods: {active_pods})...")

            except ApiException as e:
                if e.status == 404:
                    console.print(f"[bold red]Error:[/bold red] Job '{job_name}' not found while waiting.")
                    return False
                console.print(f"\n[yellow]Warning:[/yellow] API error while checking job status: {e.reason}")

            except Exception as e:
                console.print(f"\n[red]Error checking job status:[/red] {e}")

                return False 

            time.sleep(5)

    console.print(f"[bold red]Timeout waiting for Job '{job_name}' after {timeout_seconds} seconds.[/bold red]")
    return False

def _get_job_pod_logs(core_v1: client.CoreV1Api, namespace: str, job_name: str) -> Optional[str]:
    """Fetches logs from the first completed/failed pod of a Job."""
    try:

        pods = core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=f"job-name={job_name}"
        )
        if not pods.items:
            console.print(f"[yellow]Warning:[/yellow] No pods found for job '{job_name}'. Cannot fetch logs.")
            return None

        # Get logs from the first pod found (usually there's only one for simple jobs)
        pod_name = pods.items[0].metadata.name
        console.print(f"Fetching logs from pod '{pod_name}'...")


        time.sleep(2)

        log_stream = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            _preload_content=True # Get all logs at once
        )
        return log_stream
    except ApiException as e:
        console.print(f"[bold red]Error reading pod logs for job '{job_name}':[/bold red] {e.reason}")
        return None
    except Exception as e:
        console.print(f"[bold red]Unexpected error fetching pod logs:[/bold red] {e}")
        return None

def _parse_json_results_from_log(log_data: str) -> Optional[Dict[str, Any]]:
    """Parses the benchmark JSON output block from logs using start/end markers."""
    start_marker = "--- BENCHMARK RESULTS (JSON) ---"
    end_marker = "--- END BENCHMARK RESULTS ---" 

    if not isinstance(log_data, str): 
         console.print("[yellow]Warning: Invalid log data type received for parsing.[/yellow]")
         return None

    try:
        start_index = log_data.find(start_marker)
        if start_index == -1:
            console.print("[yellow]Warning:[/yellow] Benchmark JSON start marker not found in logs.")
            return None

        end_index = log_data.find(end_marker, start_index + len(start_marker))
        if end_index == -1:
            console.print("[yellow]Warning:[/yellow] Benchmark JSON end marker not found. Attempting parse from start marker to end (may include extra data).")
            json_block_text = log_data[start_index + len(start_marker):].strip()
            first_brace = json_block_text.find('{')
            last_brace = json_block_text.rfind('}')
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                 json_block_text = json_block_text[first_brace : last_brace + 1]
            else:
                 pass

        else:
            json_block_text = log_data[start_index + len(start_marker) : end_index].strip()

        if not json_block_text:
             console.print("[yellow]Warning:[/yellow] No text found between JSON markers.")
             return None
        if not json_block_text.startswith('{') or not json_block_text.endswith('}'):
            console.print(f"[yellow]Warning:[/yellow] Text between markers doesn't look like a JSON object:\n[grey50]{json_block_text[:200]}...[/grey50]")
            if end_index != -1: 
                 return None

        parsed_json = json.loads(json_block_text)
        console.print("[green]Successfully parsed benchmark results from logs.[/green]")
        return parsed_json

    except json.JSONDecodeError as e:
        console.print(f"[bold red]Error parsing JSON results from logs:[/bold red] {e}")
        max_len = 1000
        failed_block_snippet = json_block_text[:max_len] + ('...' if len(json_block_text) > max_len else '')
        console.print(f"[grey50]--- Failing Block Snippet ---[/grey50]\n{failed_block_snippet}\n[grey50]--- End Snippet ---[/grey50]")
        return None
    except Exception as e:
        console.print(f"[bold red]Error processing log results:[/bold red] {e}")
        return None

def _display_results(results_data: Dict[str, Any]):
    """Displays parsed benchmark results using Rich."""
    console.print("\nBenchmark Results:")
    stats_data = results_data.get("stats")

    if not stats_data:
        console.print("[bold yellow]No statistics block found in results.[/bold yellow]")
        errors = results_data.get("errors", [])
        if errors:
             console.print("\n[bold red]Errors reported by benchmark runner:[/bold red]")
             for i, err in enumerate(errors[:10]):
                 console.print(f"- {err}")
             if len(errors) > 10: console.print(f"...and {len(errors)-10} more.")
        return 

    # Convert stats dict back to NamedTuple for potential attribute access, or use dict directly
    # stats = BenchmarkStats(**stats_data) # Requires BenchmarkStats import

    summary_table = Table(title="Summary", show_header=False, box=None, padding=(0,1))
    summary_table.add_column(style="cyan", no_wrap=True)
    summary_table.add_column(justify="right")
    summary_table.add_row("Run Duration:", f"{results_data.get('actual_duration_seconds', 0.0):.2f} s")
    summary_table.add_row("Total Requests Run:", str(results_data.get('num_raw_results', 'N/A')))
    summary_table.add_row("Successful Requests:", str(results_data.get('num_raw_results', 0) - stats_data.get('failed_requests', 0)))
    summary_table.add_row("Failed Requests:", str(stats_data.get('failed_requests', 'N/A')))
    summary_table.add_row("Requests Per Second (RPS):", f"{stats_data.get('requests_per_second', 0.0):.2f}")
    summary_table.add_row("Total Output Tokens:", str(stats_data.get('total_output_tokens', 'N/A')))
    summary_table.add_row("Output Tokens Per Second (TPS):", f"{stats_data.get('output_tokens_per_second', 0.0):.2f}")
    console.print(summary_table)

    latency_table = Table(title="Latency (End-to-End)", show_header=False, box=None, padding=(0,1))
    latency_table.add_column(style="cyan", no_wrap=True)
    latency_table.add_column(justify="right")
    latency_table.add_row("Average:", f"{stats_data.get('avg_latency_ms', 0.0):.2f} ms" if stats_data.get('avg_latency_ms') is not None else "N/A")
    latency_table.add_row("P50 (Median):", f"{stats_data.get('p50_latency_ms', 0.0):.2f} ms" if stats_data.get('p50_latency_ms') is not None else "N/A")
    latency_table.add_row("P90:", f"{stats_data.get('p90_latency_ms', 0.0):.2f} ms" if stats_data.get('p90_latency_ms') is not None else "N/A")
    latency_table.add_row("P99:", f"{stats_data.get('p99_latency_ms', 0.0):.2f} ms" if stats_data.get('p99_latency_ms') is not None else "N/A")
    console.print(latency_table)

    errors = results_data.get("errors", [])
    if errors:
        console.print(f"\n[bold red]({len(errors)}) Errors reported by benchmark runner:[/bold red]")
        for i, err in enumerate(errors[:5]):
            console.print(f"- {err}")
        if len(errors) > 5: console.print("...")



def benchmark_deployment(
    deployment_name: Annotated[str, typer.Argument(help="The unique name of the ForgeServe deployment to benchmark.")],
    namespace: Annotated[str, typer.Option("--namespace", "-n", help="Kubernetes namespace of the deployment.")] = "default",

    prompt: Annotated[Optional[str], typer.Option("-p", "--prompt", help="A single prompt string to use (conflicts with --dataset).")] = None,
    dataset: Annotated[Optional[Path], typer.Option("--dataset", exists=True, dir_okay=False, readable=True, help="Path to a LOCAL JSON Lines file with prompts (will be passed to Job). Conflicts with --prompt.")] = None, # Dataset file is LOCAL now
    concurrency: Annotated[int, typer.Option("-c", "--concurrency", help="Number of concurrent requests.")] = 5,
    num_requests: Annotated[Optional[int], typer.Option("-N", "--num-requests", help="Total requests to send (conflicts with --duration).")] = None,
    duration: Annotated[Optional[str], typer.Option("-d", "--duration", help="Duration to run (e.g., '30s', '1m'). Conflicts with --num-requests.")] = None,
    max_tokens: Annotated[int, typer.Option("--max-tokens", help="Max output tokens per request.")] = 128,
    timeout: Annotated[int, typer.Option("--timeout", help="Request timeout in seconds.")] = 60,

    benchmark_image: Annotated[str, typer.Option(
        "--benchmark-image", help="Docker image containing the benchmark client (forgeserve benchmark runner)."
    )] = "vonhatnam121223/forgeserve-benchmark:0.0.1", 
    job_cpu: Annotated[Optional[str], typer.Option("--job-cpu", help="CPU request for the benchmark Job pod (e.g., '1', '500m').")] = "500m",
    job_memory: Annotated[Optional[str], typer.Option("--job-memory", help="Memory request for the benchmark Job pod (e.g., '1Gi').")] = "1Gi",
    job_ttl: Annotated[int, typer.Option("--job-ttl", help="Time in seconds to keep completed Job/Pod before auto-cleanup.")] = 300,
):
    """
    Benchmarks a deployed ForgeServe LLM using an in-cluster Kubernetes Job.

    Requires a benchmark client Docker image (--benchmark-image).
    Requires either --num-requests OR --duration.
    Fetches results from Job pod logs.
    """
    if job_template is None:
        console.print("[bold red]Error:[/bold red] Job template (job.yaml.j2) not loaded. Cannot proceed.")
        raise typer.Exit(code=1)

    console.print(f"Preparing benchmark Job for deployment '{deployment_name}' in namespace '{namespace}'...")

    if not prompt and not dataset:
        console.print("[bold yellow]Warning:[/yellow] No prompt or dataset specified. Using default prompt.")
    if prompt and dataset:
        console.print("[bold red]Error:[/bold red] Cannot use both --prompt and --dataset.")
        raise typer.Exit(code=1)
    if num_requests is None and duration is None:
        console.print("[bold red]Error:[/bold red] Please specify either --num-requests (-N) or --duration (-d).")
        raise typer.Exit(code=1)
    if num_requests is not None and duration is not None:
        console.print("[bold red]Error:[/bold red] Cannot use both --num-requests (-N) and --duration (-d).")
        raise typer.Exit(code=1)

    duration_seconds = None
    if duration:
        duration_seconds = _parse_duration(duration)
        if duration_seconds is None: raise typer.Exit(code=1)

    core_v1, batch_v1, apps_v1 = _get_k8s_clients()
    internal_endpoint, model_name, service_name = _find_internal_service_endpoint(apps_v1, core_v1, deployment_name, namespace)

    if not internal_endpoint or not model_name:
        console.print("[bold red]Failed to find target service details. Aborting.[/bold red]")
        raise typer.Exit(code=1)


    job_name = f"forgeserve-bench-{deployment_name}-{uuid.uuid4().hex[:6]}"
    console.print(f"   Job Name: {job_name}")
    console.print(f"   Target Endpoint (internal): {internal_endpoint}")
    console.print(f"   Benchmark Image: {benchmark_image}")


    dataset_path_in_container = None
    prompt_string_for_job = None
    if dataset:
        # TODO: Implement mounting dataset file via ConfigMap
        console.print("[bold red]Error:[/bold red] Using --dataset with Job runner is not fully implemented yet (requires ConfigMap mounting). Use --prompt for now.")
        raise typer.Exit(code=1)
    elif prompt:
         prompt_string_for_job = prompt
    else:
         prompt_string_for_job = "Explain the theory of relativity in 3 sentences."


    job_resources = {}
    if job_cpu or job_memory:
         job_resources["requests"] = {}
         if job_cpu: job_resources["requests"]["cpu"] = job_cpu
         if job_memory: job_resources["requests"]["memory"] = job_memory

    context = {
        "jobName": job_name,
        "namespace": namespace,
        "targetDeploymentName": deployment_name,
        "benchmarkImage": benchmark_image,
        "endpoint": internal_endpoint,
        "modelName": model_name,
        "concurrency": concurrency,
        "maxTokens": max_tokens,
        "timeout": timeout,
        "numRequests": num_requests,
        "durationSeconds": duration_seconds,
        "prompt": prompt_string_for_job,
        "datasetPath": dataset_path_in_container, 
        "resources": job_resources if job_resources else None,
        "ttlSecondsAfterFinished": job_ttl,
    }


    try:
        job_manifest_yaml = job_template.render(context)
        job_manifest = json.loads(json.dumps(yaml.safe_load(job_manifest_yaml))) 
        # console.print("\n--- Job Manifest ---")
        # console.print(job_manifest_yaml)
        # console.print("--- End Job Manifest ---")

        console.print(f"Creating Kubernetes Job '{job_name}'...")
        batch_v1.create_namespaced_job(body=job_manifest, namespace=namespace)
        console.print("   Job created.")

    except ApiException as e:
         console.print(f"[bold red]Error creating Job:[/bold red] Status={e.status}, Reason={e.reason}\nBody: {e.body}")
         raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]Error preparing/creating Job:[/bold red] {e}")
        raise typer.Exit(code=1)


    job_succeeded = False
    logs = None
    try:
        job_succeeded = _wait_for_job_completion(batch_v1, namespace, job_name, timeout_seconds=(duration_seconds or 60) + 120) 
        logs = _get_job_pod_logs(core_v1, namespace, job_name)

    finally:
        pass 

    if logs:
        results_data = _parse_json_results_from_log(logs)
        if results_data:
            _display_results(results_data)

            if results_data.get("stats", {}).get("failed_requests", 0) > 0:
                console.print("\n[yellow]Note: Benchmark completed, but some requests failed.[/yellow]")
                raise typer.Exit(code=1)
        else:
            console.print("[bold red]Failed to parse benchmark results from Job logs.[/bold red]")
            console.print("[grey50]Please check raw pod logs for errors.[/grey50]")
            raise typer.Exit(code=1)
    elif job_succeeded:
         console.print("[bold yellow]Job succeeded but failed to retrieve logs.[/bold yellow]")

    else:
         console.print("[bold red]Job failed and logs could not be retrieved or parsed.[/bold red]")
         raise typer.Exit(code=1)