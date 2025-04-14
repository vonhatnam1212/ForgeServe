import typer
from typing_extensions import Annotated
from typing import Optional
from rich.console import Console
from rich.table import Table

from forgeserve.runners.kubernetes import KubernetesRunner
from forgeserve.core.status_manager import StatusManager

console = Console()

def list_deployments(
    namespace: Annotated[Optional[str], typer.Option("--namespace", "-n", help="Kubernetes namespace to list deployments in.")] = "default",
):
    """
    Lists deployments managed by ForgeServe in the specified namespace.
    """
    console.print(f"Listing ForgeServe deployments in namespace '{namespace}'...")

    try:
        runner = KubernetesRunner()
        status_manager = StatusManager(runner)
    except Exception as e:
        console.print(f"[bold red]Error initializing Kubernetes connection:[/bold red] {e}")
        raise typer.Exit(code=1)

    try:
        deployments = status_manager.list_deployments(namespace)

        if not deployments:
            console.print(f"[yellow]No ForgeServe deployments found in namespace '{namespace}'.[/yellow]")
            raise typer.Exit(code=1)

        table = Table(title=f"ForgeServe Deployments in Namespace '{namespace}'", show_header=True, header_style="bold blue")
        table.add_column("Name", style="dim", width=30)
        table.add_column("Namespace", style="cyan")
        table.add_column("Desired", justify="right")
        table.add_column("Ready", justify="right")

        for dep in deployments:
            ready_str = str(dep.get('ready', 0))
            desired_str = str(dep.get('replicas', 0))
            ready_color = "green" if ready_str == desired_str else "yellow"
            table.add_row(
                dep.get('name', 'N/A'),
                dep.get('namespace', 'N/A'),
                desired_str,
                f"[{ready_color}]{ready_str}[/]"
            )

        console.print(table)

    except Exception as e:
        console.print(f"[bold red]Error listing deployments:[/bold red] {e}")
        raise typer.Exit(code=1)