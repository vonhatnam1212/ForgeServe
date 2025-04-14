import typer
from typing import Annotated, Optional

from forgeserve import __version__
from . import delete, launch, status, list_deployments, logs

app = typer.Typer(
    name="forgeserve",
    help="🔥 Deploy & manage LLM serving frameworks (vLLM, TGI, Ollama,...) on Kubernetes declaratively.",
    add_completion=False,
)

app.command(name="launch")(launch.launch_deployment)
app.command(name="delete")(delete.delete_deployment)
app.command(name="status")(status.get_deployment_status)
app.command(name="list")(list_deployments.list_deployments)
app.command(name="logs")(logs.get_deployment_logs)


def version_callback(value: bool):
    if value:
        print(f"ForgeServe CLI Version: {__version__}")
        raise typer.Exit()

@app.callback()
def main_options(
    ctx: typer.Context, 
    version: Annotated[Optional[bool], typer.Option("--version", "-v", help="Show version and exit.", callback=version_callback, is_eager=True)] = None,
):
    """
    ForgeServe CLI main entry point.
    """
    pass

if __name__ == "__main__":
    app()