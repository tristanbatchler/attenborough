from attenborough.db import queries
from attenborough.dependencies import DBConn, RequestOrigin
from attenborough.ingest.models import LoginAttempt, LoginOutcome
from attenborough.router import IngestRouter

router = IngestRouter(prefix="/logins")


@router.post("")
async def attempt_login(
    attempt: LoginAttempt, db_conn: DBConn, origin: RequestOrigin
) -> LoginOutcome:
    """Record submitted credentials and decide the outcome the decoy app shows."""
    # No decoy account exists yet, so every login fails, as a real site does for guessed
    # credentials. Deterministic on purpose: the same credentials always get the same answer.
    success = False
    await queries.create_credential_stuffing_attempt(
        db_conn,
        endpoint_path=attempt.path,
        ip_address=str(origin),
        username=attempt.username,
        password=attempt.password,
        was_fake_success=success,
    )
    return LoginOutcome(success=success)
