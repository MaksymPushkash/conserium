from scripts.run_live_eval import _score_abstention


def test_live_eval_abstention_accepts_context_provided_phrase() -> None:
    answer = "The context provided does not contain any information regarding the recommended database storage engine."

    assert _score_abstention(answer) == 1.0


def test_live_eval_abstention_accepts_does_not_contain_phrase() -> None:
    answer = "The provided context does not contain any information regarding a payroll tax rate."

    assert _score_abstention(answer) == 1.0
