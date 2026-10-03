"""The admin area: bans and the audit log, for a logged-in admin only (auth.py). To anyone else
every route is a 404, like an unknown path. Nothing here ever reaches the public exhibit except
an active ban's dates (exhibit.py, the IP summary); its reason and author stay here.
"""

from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import AfterValidator, AwareDatetime, BaseModel, Field, IPvAnyAddress

from attenborough.auth import CurrentAdmin, audit
from attenborough.db import queries
from attenborough.db.enums import AuditAction, RouterGroup
from attenborough.dependencies import DBConn
from attenborough.events import MAX_ID

router = APIRouter(prefix="/admin", tags=[RouterGroup.ADMIN])

_MAX_REASON_LENGTH = 1000
# The audit log shows this many of the latest actions.
# ponytail: no paging; add keyset paging like the exhibit's if the log outgrows one page.
_AUDIT_LOG_LENGTH = 200

BanId = Annotated[int, Path(ge=1, le=MAX_ID)]
_IP_BANS = "/ip/{ip_addr}/bans"
# Keys of the audit log's details.
_BAN_ID = "ban_id"
_REASON = "reason"


def _in_future(at: datetime | None) -> datetime | None:
    if at is not None and at <= datetime.now(UTC):
        raise ValueError("must be in the future")
    return at


class BanRecord(BaseModel):
    """A ban in full: who made it and why, and whether and why it was revoked."""

    id: int
    ip_address: str
    added: datetime
    # Null when it doesn't expire.
    expires: datetime | None
    reason: str | None
    added_by: str
    revoked_at: datetime | None
    revoked_by: str | None
    revocation_reason: str | None
    # Neither expired nor revoked.
    active: bool


class NewBan(BaseModel):
    reason: str | None = Field(default=None, max_length=_MAX_REASON_LENGTH)
    # Null for a ban that doesn't expire.
    expires: Annotated[AwareDatetime | None, AfterValidator(_in_future)] = None


class Revocation(BaseModel):
    reason: str | None = Field(default=None, max_length=_MAX_REASON_LENGTH)


class AuditEntry(BaseModel):
    id: int
    logged_at: datetime
    email: str
    action: AuditAction
    target_ip: str | None
    # A JSON object.
    details: str


def _ban_record(row: queries.ListIpBansRow) -> BanRecord:
    return BanRecord(
        id=row.id_,
        ip_address=row.ip_address,
        added=row.added,
        expires=row.expires,
        reason=row.reason,
        added_by=row.added_by,
        revoked_at=row.revoked_at,
        revoked_by=row.revoked_by,
        revocation_reason=row.revocation_reason,
        active=row.active is True,
    )


def _optional_iso(at: datetime | None) -> str | None:
    return None if at is None else at.isoformat()


@router.get("/bans")
async def list_active_bans(_admin: CurrentAdmin, db_conn: DBConn) -> list[BanRecord]:
    """Every active ban, newest first."""
    return [
        _ban_record(row) async for row in queries.list_ip_bans(db_conn, ip_address=None)
    ]


@router.get(_IP_BANS)
async def list_ip_bans(
    ip_addr: IPvAnyAddress, _admin: CurrentAdmin, db_conn: DBConn
) -> list[BanRecord]:
    """Every ban an address has had, newest first."""
    rows = queries.list_ip_bans(db_conn, ip_address=str(ip_addr))
    return [_ban_record(row) async for row in rows]


@router.post(_IP_BANS, status_code=HTTPStatus.NO_CONTENT)
async def ban_ip(
    ip_addr: IPvAnyAddress, ban: NewBan, admin: CurrentAdmin, db_conn: DBConn
) -> None:
    """Ban an address: the decoy refuses it from now on (ingest.py, judge_visit). 409 if it is
    already banned."""
    address = str(ip_addr)
    async with db_conn.transaction():
        ban_id = await queries.create_ip_ban(
            db_conn,
            ip_address=address,
            expires=ban.expires,
            reason=ban.reason,
            added_by_user_id=admin.user_id,
        )
        if ban_id is None:
            raise HTTPException(HTTPStatus.CONFLICT, "This address is already banned.")
        await audit(
            db_conn,
            admin,
            AuditAction.BAN_CREATED,
            target_ip=address,
            details={
                _BAN_ID: str(ban_id),
                _REASON: ban.reason,
                "expires": _optional_iso(ban.expires),
            },
        )


@router.post("/bans/{ban_id}/revoke", status_code=HTTPStatus.NO_CONTENT)
async def revoke_ban(
    ban_id: BanId, revocation: Revocation, admin: CurrentAdmin, db_conn: DBConn
) -> None:
    """End an active ban now. 404 if there is no active ban with that id."""
    async with db_conn.transaction():
        address = await queries.revoke_ip_ban(
            db_conn,
            id_=ban_id,
            revoked_by_user_id=admin.user_id,
            revocation_reason=revocation.reason,
        )
        if address is None:
            raise HTTPException(HTTPStatus.NOT_FOUND, "No such active ban.")
        await audit(
            db_conn,
            admin,
            AuditAction.BAN_REVOKED,
            target_ip=address,
            details={_BAN_ID: str(ban_id), _REASON: revocation.reason},
        )


@router.get("/audit")
async def list_audit_log(_admin: CurrentAdmin, db_conn: DBConn) -> list[AuditEntry]:
    """The latest admin actions, newest first."""
    rows = queries.list_audit_log(db_conn, limit_=_AUDIT_LOG_LENGTH)
    return [
        AuditEntry(
            id=row.id_,
            logged_at=row.logged_at,
            email=row.email,
            action=row.action,
            target_ip=row.target_ip,
            details=row.details,
        )
        async for row in rows
    ]
