from app.db.database import pool_kwargs


def test_local_database_uses_default_settings():
    assert pool_kwargs("postgresql://user@localhost:5432/app_db") == {}


def test_supabase_direct_connection_requires_ssl():
    kwargs = pool_kwargs("postgresql://postgres:pw@db.abcdefgh.supabase.co:5432/postgres")
    assert kwargs == {"ssl": "require", "statement_cache_size": 0}


def test_supabase_pooler_requires_ssl_and_no_statement_cache():
    kwargs = pool_kwargs("postgresql://postgres.abcdefgh:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres")
    assert kwargs == {"ssl": "require", "statement_cache_size": 0}
