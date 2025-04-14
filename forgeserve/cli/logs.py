import typer
from typing_extensions import Annotated
from typing import Optional
from rich.console import Console

from forgeserve.runners.kubernetes import KubernetesRunner
from forgeserve.core.status_manager import StatusManager

console = Console()

def get_deployment_logs(
    deployment_name: Annotated[str, typer.Argument(help="The unique name of the deployment.")],
    namespace: Annotated[Optional[str], typer.Option("--namespace", "-n", help="Kubernetes namespace where the deployment exists.")] = "default",
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Specify if the logs should be streamed continuously.")] = False,
    tail: Annotated[Optional[int], typer.Option("--tail", help="Number of lines from the end of the logs to show. Defaults to showing all logs.")] = None,
):
    """
    Fetches or streams logs from the pod(s) of a deployment.
    """
    action = "Streaming" if follow else "Fetching"
    console.print(f"{action} logs for deployment '{deployment_name}' in namespace '{namespace}'...")
    if tail:
        console.print(f"   Showing last {tail} lines.")
    if follow:
        console.print("   (Press Ctrl+C to stop streaming)")

    try:
        runner = KubernetesRunner()
        status_manager = StatusManager(runner)
    except Exception as e:
        console.print(f"[bold red]Error initializing Kubernetes connection:[/bold red] {e}")
        raise typer.Exit(code=1)

    log_generator = None
    try:
        log_generator = status_manager.get_logs(deployment_name, namespace, follow, tail)
        for line in log_generator:
            if "error" in line.lower():
                console.print(f"[red]{line}[/red]")
            elif "warn" in line.lower():
                 console.print(f"[yellow]{line}[/yellow]")
            else:
                console.print(line)

    except KeyboardInterrupt:
        if follow:
            console.print("\n[bold yellow]Log streaming stopped by user.[/bold yellow]")
        raise typer.Exit()
    except Exception as e:
        console.print(f"\n[bold red]Error fetching logs for '{deployment_name}':[/bold red] {e}")
        raise typer.Exit(code=1)
    finally:
        # Ensure the generator (and underlying connection) is properly closed
        # The Kubernetes client library's stream object should handle this on iteration end/exception,
        # but explicit closing if available is good practice. The runner's get_logs handles this.
        pass