import typer
from typing_extensions import Annotated
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.padding import Padding

from forgeserve.runners.kubernetes import KubernetesRunner
from forgeserve.core.status_manager import StatusManager

console = Console()

def get_deployment_status(
    deployment_name: Annotated[str, typer.Argument(help="The unique name of the deployment.")],
    namespace: Annotated[Optional[str], typer.Option("--namespace", "-n", help="Kubernetes namespace where the deployment exists.")] = "default",
):
    """
    Checks the status of a specific ForgeServe deployment.
    """
    console.print(f"Checking status for deployment '{deployment_name}' in namespace '{namespace}'...")

    try:
        runner = KubernetesRunner()
        status_manager = StatusManager(runner)
    except Exception as e:
        console.print(f"[bold red]Error initializing Kubernetes connection:[/bold red] {e}")
        raise typer.Exit(code=1)

    try:
        status = status_manager.get_status(deployment_name, namespace)

        if not status:
            console.print(f"[bold yellow]Deployment '{deployment_name}' not found or status could not be retrieved in namespace '{namespace}'.[/bold yellow]")
            raise typer.Exit(code=1)

        console.print(f"\n[bold green]Status for Deployment: {status.name}[/bold green]")

        summary_table = Table.grid(padding=(0, 1))
        summary_table.add_column()
        summary_table.add_column()
        summary_table.add_row("[cyan]Namespace:[/cyan]", status.namespace)
        summary_table.add_row("[cyan]Desired Replicas:[/cyan]", str(status.desired_replicas))
        summary_table.add_row("[cyan]Ready Replicas:[/cyan]", f"[bold {'green' if status.ready_replicas == status.desired_replicas else 'yellow'}]{status.ready_replicas}[/]")
        summary_table.add_row("[cyan]Service Endpoint:[/cyan]", status.service_endpoint if status.service_endpoint else "[grey50]Not Available[/grey50]")

        console.print(Panel(summary_table, title="Overview", border_style="blue", expand=False))
        if status.pods:
            pods_table = Table(title="Pods", show_header=True, header_style="bold magenta", border_style="dim")
            pods_table.add_column("Pod Name", style="dim", width=40)
            pods_table.add_column("Status", justify="center")
            pods_table.add_column("Ready", justify="center")
            pods_table.add_column("Node", style="cyan")
            pods_table.add_column("Start Time", style="green")

            for pod in status.pods:
                ready_status = "[bold green]True[/]" if pod.get('ready') else "[bold yellow]False[/]"
                pod_status = pod.get('status', 'Unknown')
                status_color = "green" if pod_status == "Running" else ("yellow" if pod_status in ["Pending", "ContainerCreating"] else "red")

                pods_table.add_row(
                    pod.get('name', 'N/A'),
                    f"[{status_color}]{pod_status}[/]",
                    ready_status,
                    pod.get('node', 'N/A'),
                    pod.get('startTime', 'N/A')
                )
            console.print(Padding(pods_table, (1, 0)))
        else:
            console.print(Padding("[yellow]No pods found for this deployment.[/yellow]", (1, 0)))

    except Exception as e:
        console.print(f"[bold red]Error fetching status for '{deployment_name}':[/bold red] {e}")
        raise typer.Exit(code=1)