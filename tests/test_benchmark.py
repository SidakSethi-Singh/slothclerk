from fastapi.testclient import TestClient
from app.main import app
from app.services.benchmark_service import benchmark_service, CLOUD_PRICING_MODELS


def test_benchmark_service_savings_calculation():
    savings = benchmark_service.calculate_cost_savings(docs_per_month=1000, avg_tokens_per_doc=10000)
    assert savings["docs_per_month"] == 1000
    assert savings["total_monthly_tokens"] == 10_000_000
    assert "GPT-4o (OpenAI)" in savings["cloud_comparisons"]
    assert "Claude 3.5 Sonnet (Anthropic)" in savings["cloud_comparisons"]
    assert savings["cloud_comparisons"]["GPT-4o (OpenAI)"]["annual_savings"] > 0
    assert savings["pii_records_protected"] == 100_000


def test_benchmark_service_local_run():
    res = benchmark_service.run_local_benchmark()
    assert "extraction_ms" in res
    assert "chunking_ms" in res
    assert "total_chunks" in res
    assert res["total_chunks"] >= 0
    assert res["throughput_chars_per_sec"] >= 0


def test_api_benchmark_endpoint():
    client = TestClient(app)
    resp = client.get("/api/benchmark")
    assert resp.status_code == 200
    data = resp.json()
    assert "cloud_pricing_matrix" in data
    assert "savings_model" in data


def test_api_benchmark_calculate_endpoint():
    client = TestClient(app)
    resp = client.post("/api/benchmark/calculate", json={"docs_per_month": 2000, "avg_tokens_per_doc": 15000})
    assert resp.status_code == 200
    data = resp.json()
    assert data["docs_per_month"] == 2000
    assert data["total_monthly_tokens"] == 30_000_000
