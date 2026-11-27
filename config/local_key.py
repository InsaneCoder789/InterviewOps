"""A secret key for local work, generated on first use so none is kept in the code."""

import contextlib
import os
import secrets
import tempfile


def local_secret_key(path):
    """Read the key at `path`, creating it first. Safe when processes start together."""
    if not path.exists():
        handle, draft = tempfile.mkstemp(dir=path.parent, prefix=path.name)
        with os.fdopen(handle, "w") as file:
            file.write(secrets.token_urlsafe(50))
        try:
            # Linking fails if another process got there first, and never exposes
            # a half-written key.
            with contextlib.suppress(FileExistsError):
                os.link(draft, path)
        finally:
            os.unlink(draft)
    return path.read_text().strip()
