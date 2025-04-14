import time
from typing import List, Dict, Any, Optional, Generator
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from .base import BaseRunner, DeploymentStatus
from .._version import __version__ 

try:
    config.load_kube_config() 
    print("Kubernetes config loaded successfully.")
except config.ConfigException:
    print("Warning: Could not load Kubernetes config. Assuming in-cluster or manual config.")
  


class KubernetesRunner(BaseRunner):
    """Runner implementation using the Kubernetes Python client."""

    def __init__(self):
        self.apps_v1_api = client.AppsV1Api()
        self.core_v1_api = client.CoreV1Api()
        

    def _get_common_labels(self, deployment_name: str) -> Dict[str, str]:
         """Generate standard labels including version."""
         labels = super()._get_common_labels(deployment_name)
         labels["app.kubernetes.io/version"] = __version__
         return labels

    def _add_common_metadata(self, resource: Dict[str, Any], deployment_name: str, namespace: str, custom_labels: Dict[str, str], custom_annotations: Dict[str, str]):
         """Inject standard labels and metadata into resource manifests."""
         if 'metadata' not in resource:
             resource['metadata'] = {}
         resource['metadata']['namespace'] = namespace
         resource['metadata']['name'] = resource['metadata'].get('name', f"{deployment_name}-{resource['kind'].lower()}")

         common_labels = self._get_common_labels(deployment_name)
         resource['metadata']['labels'] = {**common_labels, **custom_labels, **resource['metadata'].get('labels', {})}

         if resource['kind'] in ['Deployment', 'StatefulSet'] and 'spec' in resource and 'selector' in resource['spec']:
              resource['spec']['selector']['matchLabels'] = {**common_labels, **resource['spec']['selector'].get('matchLabels', {})}
              if 'template' in resource['spec'] and 'metadata' in resource['spec']['template']:
                   resource['spec']['template']['metadata']['labels'] = {**common_labels, **custom_labels, **resource['spec']['template']['metadata'].get('labels', {})}
         if resource['kind'] == 'Service' and 'spec' in resource:
              resource['spec']['selector'] = {**common_labels, **resource['spec'].get('selector', {})}

         resource['metadata']['annotations'] = {**custom_annotations, **resource['metadata'].get('annotations', {})}
         return resource

    def apply(self, manifests: List[Dict[str, Any]], namespace: str, deployment_name: str, custom_labels: Dict[str,str], custom_annotations: Dict[str, str]):
        """Apply Kubernetes resources using server-side apply or create/patch."""
        for manifest in manifests:
            kind = manifest.get("kind")
            manifest = self._add_common_metadata(manifest, deployment_name, namespace, custom_labels, custom_annotations)
            name = manifest.get("metadata", {}).get("name")

            if not kind or not name:
                print(f"Warning: Skipping manifest missing kind or metadata.name: {manifest}")
                continue

            print(f"Applying {kind}: {namespace}/{name}...")
            try:
                if kind == "Deployment":
                    try:
                        self.apps_v1_api.read_namespaced_deployment(name, namespace)
                        resp = self.apps_v1_api.patch_namespaced_deployment(name, namespace, manifest)
                        print(f"Patched Deployment {namespace}/{name}")
                    except ApiException as e:
                        if e.status == 404: 
                            resp = self.apps_v1_api.create_namespaced_deployment(namespace, manifest)
                            print(f"Created Deployment {namespace}/{name}")
                        else:
                            raise 
                elif kind == "Service":
                     try:
                        self.core_v1_api.read_namespaced_service(name, namespace)
                        resp = self.core_v1_api.patch_namespaced_service(name, namespace, manifest)
                        print(f"Patched Service {namespace}/{name}")
                     except ApiException as e:
                        if e.status == 404:
                            resp = self.core_v1_api.create_namespaced_service(namespace, manifest)
                            print(f"Created Service {namespace}/{name}")
                        else:
                            raise
                elif kind == "ConfigMap":
                     try:
                        self.core_v1_api.read_namespaced_config_map(name, namespace)
                        resp = self.core_v1_api.patch_namespaced_config_map(name, namespace, manifest)
                        print(f"Patched ConfigMap {namespace}/{name}")
                     except ApiException as e:
                        if e.status == 404:
                            resp = self.core_v1_api.create_namespaced_config_map(namespace, manifest)
                            print(f"Created ConfigMap {namespace}/{name}")
                        else:
                            raise
                else:
                    print(f"Warning: Applying kind '{kind}' not fully implemented yet. Use kubectl apply for now.")

            except ApiException as e:
                print(f"Error applying {kind} {namespace}/{name}: {e.status} {e.reason}\nBody: {e.body}")
                # Decide whether to continue or raise based on error type
                if e.status != 409:
                    raise
            except Exception as e:
                print(f"Unexpected error applying {kind} {namespace}/{name}: {e}")
                raise


    def delete(self, name: str, namespace: str, labels: Dict[str, str]):
        """Delete Deployment and Service by common labels."""
        print(f"Deleting resources for deployment '{name}' in namespace '{namespace}'...")
        label_selector = ",".join(f"{k}={v}" for k, v in labels.items())

        # Delete Deployment
        try:
            print(f"Deleting Deployment with labels: {label_selector}")
            self.apps_v1_api.delete_collection_namespaced_deployment(
                namespace=namespace,
                label_selector=label_selector,
                propagation_policy='Foreground'
            )
            # Note: delete_collection might not wait. Add polling if needed.
            print(f"Deployment deletion initiated for {name}.")
        except ApiException as e:
            if e.status != 404:
                print(f"Error deleting Deployment for {name}: {e}")
            else:
                 print(f"Deployment for {name} not found (already deleted?).")


        # Delete Service
        try:
            print(f"Deleting Service with labels: {label_selector}")
            self.core_v1_api.delete_collection_namespaced_service(
                namespace=namespace,
                label_selector=label_selector
            )
            print(f"Service deletion initiated for {name}.")
        except ApiException as e:
            if e.status != 404:
                print(f"Error deleting Service for {name}: {e}")
            else:
                 print(f"Service for {name} not found (already deleted?).")

    def get_status(self, name: str, namespace: str, labels: Dict[str, str]) -> Optional[DeploymentStatus]:
        """Get deployment, pod, and service status."""
        label_selector = ",".join(f"{k}={v}" for k, v in labels.items())
        deployment = None
        pods_info = []
        service_endpoint = None

        try:
            deployments = self.apps_v1_api.list_namespaced_deployment(namespace, label_selector=label_selector)
            if deployments.items:
                deployment = deployments.items[0]
            else:
                 print(f"Deployment '{name}' not found in namespace '{namespace}'.")
                 return None

            pods = self.core_v1_api.list_namespaced_pod(namespace, label_selector=label_selector)
            for pod in pods.items:
                pods_info.append({
                    "name": pod.metadata.name,
                    "status": pod.status.phase,
                    "ready": all(cs.ready for cs in pod.status.container_statuses or []),
                    "node": pod.spec.node_name,
                    "startTime": pod.status.start_time.isoformat() if pod.status.start_time else None,
                })

            services = self.core_v1_api.list_namespaced_service(namespace, label_selector=label_selector)
            if services.items:
                 service = services.items[0]
                 if service.spec.cluster_ip and service.spec.ports:
                      port = service.spec.ports[0].port
                      service_endpoint = f"{service.spec.cluster_ip}:{port}"

            status = DeploymentStatus(
                name=name,
                namespace=namespace,
                desired_replicas=deployment.spec.replicas,
                ready_replicas=deployment.status.ready_replicas if deployment.status.ready_replicas else 0,
                pods=pods_info,
                service_endpoint=service_endpoint
            )
            return status

        except ApiException as e:
            print(f"Error getting status for {name}: {e}")
            return None
        except Exception as e:
             print(f"Unexpected error getting status for {name}: {e}")
             return None


    def get_logs(self, name: str, namespace: str, labels: Dict[str, str], follow: bool = False, tail_lines: Optional[int] = None) -> Generator[str, None, None]:
        """Stream or retrieve logs from the first pod matching the labels."""
        label_selector = ",".join(f"{k}={v}" for k, v in labels.items())
        try:
            pods = self.core_v1_api.list_namespaced_pod(namespace, label_selector=label_selector)
            if not pods.items:
                print(f"No pods found for deployment {name} in namespace {namespace}.")
                return

            pod_name = pods.items[0].metadata.name 
            print(f"Fetching logs for pod: {pod_name} (follow={follow}, tail={tail_lines})...")

            log_stream = self.core_v1_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                follow=follow,
                tail_lines=tail_lines,
                pretty=False, 
                timestamps=True,
                _preload_content=False 
            )

            for line in log_stream:
                yield line.decode('utf-8').strip() 

        except ApiException as e:
            print(f"Error getting logs for {name} (pod: {pod_name if 'pod_name' in locals() else 'unknown'}): {e}")

        except Exception as e:
             print(f"Unexpected error getting logs for {name}: {e}")
        finally:
             if 'log_stream' in locals() and hasattr(log_stream, 'release_conn'):
                  log_stream.release_conn() 