import hoordu
import contextvars

_HOORDU_SESSION = contextvars.ContextVar('_HOORDU_SESSION', default=None)

class ContextSession:
    def __getattr__(self, name):
        current_session = _HOORDU_SESSION.get()
        if current_session is None:
            raise RuntimeError('No session was created for this context')
        return getattr(current_session, name)

session: hoordu.HoorduSession = ContextSession()

class ContextSessionDepedency:
    def __init__(self, hrd: hoordu.hoordu):
        self.hrd = hrd

    async def __call__(self) -> hoordu.HoorduSession:
        async with self.hrd.session() as session:
            token = _HOORDU_SESSION.set(session)
            yield session
            _HOORDU_SESSION.reset(token)
