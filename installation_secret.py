"""A private, persistent signing key; never a public repository default."""
import os
import secrets
from pathlib import Path
from sqlalchemy.engine import make_url


def installation_secret(app):
    configured = app.config.get('SECRET_KEY')
    if configured:
        if len(configured) < 32 or configured == '8BYkEfBA6O6donzWlSihBXox7C0sKR6b':
            raise ValueError('APP_SECRET_KEY must be a private random key of at least 32 characters.')
        return configured
    url = app.config['SQLALCHEMY_BINDS']['users']
    url = make_url(url['url'] if isinstance(url, dict) else url)
    if url.database == ':memory:':
        return secrets.token_hex(32)
    directory = Path(app.instance_path)
    if url.get_backend_name() == 'sqlite' and url.database:
        database = Path(url.database)
        directory = database.parent if database.is_absolute() else directory / database.parent
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / '.session-secret'
    # Atomic publication: no process can observe a partially written key.
    temporary = directory / ('.session-secret-' + secrets.token_hex(12))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(secrets.token_hex(32))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        temporary.unlink()
    key = path.read_text().strip()
    if len(key) < 64:
        raise ValueError('Invalid installation signing key; restore the private .session-secret file.')
    return key
