import argparse
import json
import asyncio
import sys
import time
from pathlib import Path

try:
    from forgeserve.benchmark.client import BenchmarkClient
    from forgeserve.benchmark.metrics import calculate_stats
except ImportError as e:
    print(f"ERROR: Failed to import benchmark modules. Check installation in Docker image. {e}", file=sys.stderr)
    sys.exit(1)

def _load_prompts_from_jsonl(dataset_path: str) -> list[str]:
    """Loads prompts from a JSONL file path."""
    prompts = []
    print(f"Attempting to load prompts from: {dataset_path}")
    try:
        with open(dataset_path, 'r') as f:
            for i, line in enumerate(f):
                try:
                    data = json.loads(line)
                    if "prompt" in data and isinstance(data["prompt"], str):
                        prompts.append(data["prompt"])
                    else:
                         print(f"Warning: Skipping invalid line {i+1} in dataset: {line.strip()}", file=sys.stderr)
                except json.JSONDecodeError:
                    print(f"Warning: Skipping non-JSON line {i+1} in dataset: {line.strip()}", file=sys.stderr)
        if not prompts:
            raise ValueError(f"No valid prompts found in dataset file: {dataset_path}")
        print(f"Loaded {len(prompts)} prompts.")
        return prompts
    except FileNotFoundError:
         print(f"ERROR: Dataset file not found at path: {dataset_path}", file=sys.stderr)
         raise
    except Exception as e:
        print(f"ERROR: Failed to read dataset file {dataset_path}: {e}", file=sys.stderr)
        raise

async def main():
    parser = argparse.ArgumentParser(description="ForgeServe Benchmark Runner (runs inside K8s Job)")
    parser.add_argument("--endpoint", required=True, help="Target service endpoint URL (e.g., http://service.ns.svc:8000)")
    parser.add_argument("--model-name", required=True, help="Model name to use in API requests")
    parser.add_argument("--concurrency", type=int, required=True, help="Number of concurrent clients")
    parser.add_argument("--max-tokens", type=int, required=True, help="Max output tokens per request")
    parser.add_argument("--timeout", type=int, default=60, help="Request timeout in seconds")

    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="Single prompt string")
    prompt_group.add_argument("--dataset-path", help="Path to JSONL dataset file within the container (if mounted)") # Path *inside container*

    run_group = parser.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--num-requests", type=int, help="Total number of requests")
    run_group.add_argument("--duration-seconds", type=int, help="Duration to run in seconds")

    args = parser.parse_args()


    prompts = []
    try:
        if args.dataset_path:
            if not Path(args.dataset_path).is_file():
                 print(f"ERROR: Specified dataset path '{args.dataset_path}' does not exist or is not a file inside the container.", file=sys.stderr)
                 sys.exit(1)
            prompts = _load_prompts_from_jsonl(args.dataset_path)
        elif args.prompt:
            prompts = [args.prompt]
    except Exception as e:
         print(f"ERROR: Failed to load prompts: {e}", file=sys.stderr)
         sys.exit(1)

    if not prompts:
         print("ERROR: No valid prompts available.", file=sys.stderr)
         sys.exit(1)

    print("Initializing benchmark client...")
    client = BenchmarkClient(
        endpoint=args.endpoint,
        model_name=args.model_name,
        prompts=prompts,
        concurrency=args.concurrency,
        max_tokens=args.max_tokens,
        num_requests=args.num_requests,
        duration_seconds=args.duration_seconds,
        timeout_seconds=args.timeout
    )

    print(f"Starting benchmark run against {args.endpoint}...")
    start_run_time = time.time()
    try:
        results = await client.run()
    except Exception as e:
        print(f"\nERROR: Benchmark execution failed: {e}", file=sys.stderr)
        if client.results:
            print("\n--- PARTIAL RESULTS (JSON) ---")
            print(json.dumps([r.model_dump() for r in client.results], indent=2)) 
        sys.exit(1) 

    end_run_time = time.time()
    actual_duration = end_run_time - start_run_time
    print("Benchmark run finished.")


    print("Calculating statistics...")
    stats = calculate_stats(results, total_duration_override=args.duration_seconds or actual_duration)


    output_data = {
        "stats": stats._asdict() if stats else None,
        "config": vars(args), 
        "actual_duration_seconds": actual_duration,

        "num_raw_results": len(results),
        "errors": [r.error for r in results if r.error]
    }
    print("\n--- BENCHMARK RESULTS (JSON) ---")
    try:
        print(json.dumps(output_data, indent=2))
    except TypeError as e:
        print(f"Error serializing results to JSON: {e}", file=sys.stderr)
        del output_data["stats"]
        try:
             print(json.dumps(output_data, indent=2))
        except Exception as e_inner:
             print(f"Fallback JSON serialization failed: {e_inner}", file=sys.stderr)
             print("Failed to generate JSON output.", file=sys.stderr)
    finally:
        print("--- END BENCHMARK RESULTS ---")


    if stats and stats.failed_requests == 0:
         print("Benchmark completed successfully.")
         sys.exit(0)
    elif stats:
         print(f"Benchmark completed with {stats.failed_requests} failed requests.")
         sys.exit(0) 
    else:
         print("Benchmark completed, but no stats could be calculated (all requests failed?).")
         sys.exit(1) 

if __name__ == "__main__":
    asyncio.run(main())