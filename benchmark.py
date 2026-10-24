#!/usr/bin/env python3
"""
SlothClerk Cloud Benchmark Suite
Evaluates local offline latency, extraction throughput, privacy score, and cost savings vs Cloud LLMs.
"""

import sys
import os
import json
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.benchmark_service import benchmark_service, CLOUD_PRICING_MODELS


def run_cli_benchmark():
    print("\n" + "=" * 70)
    print(" [SlothClerk] Cloud vs Local Offline Benchmark Suite")
    print("=" * 70)

    print("\n[1/3] Benchmarking Local Ingestion Pipeline...")
    results = benchmark_service.run_local_benchmark()

    print(f"  • Target File:       {results['target_document']}")
    print(f"  • Extraction Time:   {results['extraction_ms']} ms")
    print(f"  • Chunking Time:     {results['chunking_ms']} ms")
    print(f"  • Total Chunks:      {results['total_chunks']}")
    print(f"  • Throughput:        {results['throughput_chars_per_sec']:,} chars/sec")
    print(f"  • Local Ollama LLM:  {results['local_model']} ({results['ollama_status']})")

    print("\n[2/3] Privacy & Model Architecture Comparison Matrix:")
    print("-" * 70)
    print(f"{'Provider / Model':<30} | {'Latency':<10} | {'Cost / 1M':<12} | {'Privacy'}")
    print("-" * 70)
    for name, data in CLOUD_PRICING_MODELS.items():
        cost_str = f"${data['input_cost_per_m']:.2f} / ${data['output_cost_per_m']:.2f}"
        lat_str = f"~{data['avg_latency_ms']}ms"
        priv_str = "Airgapped (A+)" if data["offline_capable"] else "Cloud PII Risk (F)"
        print(f"{name:<30} | {lat_str:<10} | {cost_str:<12} | {priv_str}")
    print("-" * 70)

    print("\n[3/3] Enterprise ROI & Annual Cloud Cost Avoidance:")
    print("  (Basis: 1,500 legal documents / month @ 12,000 tokens / doc = 18M tokens/mo)")
    print("-" * 70)
    savings = benchmark_service.calculate_cost_savings(docs_per_month=1500, avg_tokens_per_doc=12000)
    for provider, s in savings["cloud_comparisons"].items():
        print(f"  • vs {provider:<26}: Save ${s['annual_savings']:,.2f} USD / year")
    print(f"  • PII Breaches Prevented:       {savings['pii_records_protected']:,} sensitive entities retained locally")
    print("=" * 70)
    print("[OK] Benchmark completed successfully. SlothClerk delivers 100% data sovereignty.\n")


if __name__ == "__main__":
    run_cli_benchmark()
