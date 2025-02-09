# mypy: ignore-errors
import pytest

from sieves import Pipeline, tasks
from sieves.engines import EngineType


@pytest.mark.parametrize(
    "batch_engine",
    [EngineType.huggingface],
    indirect=["batch_engine"],
)
def test_run(dummy_docs, batch_engine) -> None:
    """Tests whether chunking mechanism in PredictiveTask works as expected."""
    chunk_interval = 5
    pipe = Pipeline([tasks.preprocessing.NaiveChunker(interval=chunk_interval)])
    docs = list(pipe(dummy_docs))

    assert len(docs) == 2
    for doc in docs:
        assert doc.text
        assert len(doc.chunks) == 2


def test_serialization(dummy_docs) -> None:
    chunk_interval = 5
    pipe = Pipeline(tasks=[tasks.preprocessing.NaiveChunker(interval=chunk_interval)])
    docs = list(pipe(dummy_docs))

    config = pipe.serialize()
    assert config.model_dump() == {
        "cls_name": "sieves.pipeline.core.Pipeline",
        "tasks": {
            "is_placeholder": False,
            "value": [
                {
                    "cls_name": "sieves.tasks.preprocessing.chunkers.NaiveChunker",
                    "include_meta": {"is_placeholder": False, "value": False},
                    "interval": {"is_placeholder": False, "value": 5},
                    "show_progress": {"is_placeholder": False, "value": True},
                    "task_id": {"is_placeholder": False, "value": "NaiveChunker"},
                    "version": "0.6.0",
                }
            ],
        },
        "version": "0.6.0",
    }

    deserialized_pipeline = Pipeline.deserialize(config=config, tasks_kwargs=[{}])
    assert docs[0] == list(deserialized_pipeline(dummy_docs))[0]
