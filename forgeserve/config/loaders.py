import yaml
from pathlib import Path
from typing import Dict, Any
from pydantic import ValidationError

from .models import DeploymentConfig

def load_config_from_yaml(filepath: Path) -> DeploymentConfig:
    """Loads and validates deployment configuration from a YAML file."""
    try:
        with open(filepath, 'r') as f:
            raw_config = yaml.safe_load(f)
        if not isinstance(raw_config, dict):
            raise ValueError(f"Invalid YAML format in {filepath}, expected a dictionary.")
        return DeploymentConfig(**raw_config)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {filepath}")
        raise
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file {filepath}: {e}")
        raise
    except ValidationError as e:
        print(f"Error validating configuration from {filepath}:\n{e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred loading config from {filepath}: {e}")
        raise

def load_config_from_dict(config_dict: Dict[str, Any]) -> DeploymentConfig:
    """Loads and validates deployment configuration from a dictionary."""
    try:
        return DeploymentConfig(**config_dict)
    except ValidationError as e:
        print(f"Error validating configuration dictionary:\n{e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred loading config from dict: {e}")
        raise