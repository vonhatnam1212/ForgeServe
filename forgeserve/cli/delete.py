import typer
from typing_extensions import Annotated

from forgeserve.runners.kubernetes import KubernetesRunner
from forgeserve.core.deployment_manager import DeploymentManager

def delete_deployment(
    deployment_name: Annotated[str, typer.Argument(help="The unique name of the ForgeServe deployment to delete.")],
    namespace: Annotated[str, typer.Option("--namespace", "-n", help="The Kubernetes namespace where the deployment exists.")] = "default",
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt before deleting.")] = False,
):
    """
    Deletes a ForgeServe deployment and associated resources from Kubernetes.

    This typically removes the Kubernetes Deployment and Service objects
    managed by ForgeServe for the specified deployment name.
    """
    print(f"Attempting to delete deployment '{deployment_name}' in namespace '{namespace}'...")

    if not yes:
        typer.echo(f"This will delete the Kubernetes resources associated with the '{deployment_name}' deployment.")
        confirmed = typer.confirm("Are you sure you want to proceed?")
        if not confirmed:
            print("Aborted.")
            raise typer.Exit()

    try:
        runner = KubernetesRunner()
    except Exception as e:
        print(f"Error initializing Kubernetes connection: {e}")
        print("Ensure kubectl is configured correctly or you are running in-cluster.")
        raise typer.Exit(code=1)

    manager = DeploymentManager(runner)

    try:
        manager.down(deployment_name, namespace)
        print(f"Successfully initiated teardown for deployment '{deployment_name}'.")
        print("Kubernetes will now terminate the associated resources.")
    except Exception as e:
        print(f"Error during teardown for '{deployment_name}': {e}")
        raise typer.Exit(code=1)
