from regtracker.common.config import load_instruments


def test_sources_file_loads() -> None:
    instruments = load_instruments()
    assert len(instruments) >= 3
    assert all(i.celex_base for i in instruments)
    assert len({i.doc_id for i in instruments}) == len(instruments)
