import typer
from .cli.main import app as cli_app

def main():
    """Main entry point for running the CLI."""
    cli_app()

if __name__ == "__main__":
    main()