# forgeserve/benchmark/metrics.py
from typing import List, Dict, Optional, NamedTuple
import time
import numpy as np
from pydantic import BaseModel

class RequestResult(BaseModel):
    """Stores results for a single request."""
    success: bool
    latency_ms: Optional[float] = None
    output_tokens: Optional[int] = None
    error: Optional[str] = None
    start_time: float 
    end_time: float   

class BenchmarkStats(NamedTuple):
    """Aggregated benchmark statistics."""
    total_requests: int
    failed_requests: int
    total_time_seconds: float
    requests_per_second: float
    total_output_tokens: int
    output_tokens_per_second: float
    avg_latency_ms: Optional[float]
    p50_latency_ms: Optional[float]
    p90_latency_ms: Optional[float]
    p99_latency_ms: Optional[float]

def calculate_stats(results: List[RequestResult], total_duration_override: Optional[float] = None) -> Optional[BenchmarkStats]:
    """Calculates summary statistics from a list of request results."""
    if not results:
        return None

    successful_results = [r for r in results if r.success and r.latency_ms is not None]
    failed_requests = len(results) - len(successful_results)

    if not successful_results:
        first_req_start = min(r.start_time for r in results) if results else time.time()
        last_req_end = max(r.end_time for r in results) if results else first_req_start
        total_time = total_duration_override or (last_req_end - first_req_start)
        return BenchmarkStats(
            total_requests=len(results),
            failed_requests=failed_requests,
            total_time_seconds=total_time,
            requests_per_second=0.0,
            total_output_tokens=0,
            output_tokens_per_second=0.0,
            avg_latency_ms=None,
            p50_latency_ms=None,
            p90_latency_ms=None,
            p99_latency_ms=None,
        )


    latencies_ms = np.array([r.latency_ms for r in successful_results])
    output_tokens_list = [r.output_tokens for r in successful_results if r.output_tokens is not None]
    total_output_tokens = sum(output_tokens_list)

    if total_duration_override:
        total_time = total_duration_override
    else:
        first_req_start = min(r.start_time for r in successful_results)
        last_req_end = max(r.end_time for r in successful_results)
        total_time = last_req_end - first_req_start

    total_time = max(total_time, 0.001) # Avoid division by zero

    rps = len(successful_results) / total_time
    tps = total_output_tokens / total_time

    return BenchmarkStats(
        total_requests=len(results),
        failed_requests=failed_requests,
        total_time_seconds=total_time,
        requests_per_second=rps,
        total_output_tokens=total_output_tokens,
        output_tokens_per_second=tps,
        avg_latency_ms=float(np.mean(latencies_ms)) if len(latencies_ms) > 0 else None,
        p50_latency_ms=float(np.percentile(latencies_ms, 50)) if len(latencies_ms) > 0 else None,
        p90_latency_ms=float(np.percentile(latencies_ms, 90)) if len(latencies_ms) > 0 else None,
        p99_latency_ms=float(np.percentile(latencies_ms, 99)) if len(latencies_ms) > 0 else None,
    )