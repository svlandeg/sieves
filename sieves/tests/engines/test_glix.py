# mypy: ignore-errors
import pytest

from sieves import Pipeline, engines, tasks


@pytest.mark.parametrize(
    "engine",
    [engines.EngineType.glix],
    indirect=True,
)
def test_run(dummy_docs, engine) -> None:
    pipe = Pipeline(
        [
            tasks.predictive.Classification(task_id="classifier", labels=["science", "politics"], engine=engine),
        ]
    )
    docs = list(pipe(dummy_docs))

    assert len(docs) == 2
    for doc in docs:
        assert doc.text
        assert doc.results["classifier"]
        assert "classifier" in doc.results
