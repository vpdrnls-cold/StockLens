def test_scaffold_imports():
    import app
    assert callable(app.main)
