from scripts.run_eval_harness import _threshold_failures


def test_threshold_failures_include_metric_values_and_required_minimums() -> None:
    failures = _threshold_failures(
        summary={"faithfulness": 0.79, "answer_relevancy": 0.7, "context_recall": 0.5},
        thresholds={"faithfulness": 0.8, "answer_relevancy": 0.6, "context_recall": 0.6},
    )

    assert failures == [
        "faithfulness: 0.7900 < required 0.8000",
        "context_recall: 0.5000 < required 0.6000",
    ]
