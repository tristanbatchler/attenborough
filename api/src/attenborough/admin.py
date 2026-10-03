"""The admin area: bans, response rules (rules.py) and the audit log, for a logged-in admin only
(auth.py). To anyone else every route is a 404, like an unknown path. Nothing here ever reaches the
public exhibit except an active ban's dates (exhibit.py, the IP summary) and whether a rule answered
a hit; reasons, authors, rules and notes stay here.
"""

from datetime import UTC, datetime
from enum import StrEnum
from http import HTTPMethod, HTTPStatus
from typing import Annotated, ClassVar

from fastapi import APIRouter, HTTPException, Path
from liquid2.exceptions import LiquidError
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    IPvAnyAddress,
)

from attenborough import rules
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
RuleId = Annotated[int, Path(ge=1, le=MAX_ID)]
_RULE = "/rules/{rule_id}"
_IP_BANS = "/ip/{ip_addr}/bans"
# Keys of the audit log's details.
_BAN_ID = "ban_id"
_RULE_ID = "rule_id"
_MOVED = "moved"
_NO_SUCH_RULE = "No such rule."
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


class RuleRecord(rules.RuleForm):
    """A saved rule, with how many hits it answered."""

    # Every field is there in a response, defaults or not.
    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_serialization_defaults_required=True
    )

    id: int
    position: int
    updated: datetime
    hits: int


class NewRule(BaseModel):
    id: int


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"


class Move(BaseModel):
    direction: Direction


class PreviewRequest(BaseModel):
    """A rule, and the request to try it on: as if `ip` had sent it."""

    rule: rules.RuleForm
    ip: IPvAnyAddress
    method: str = Field(default=HTTPMethod.GET, min_length=1, max_length=32)
    path: str = Field(default=rules.ROOT_PATH, max_length=rules.MAX_PREVIEW_PATH)


class Preview(BaseModel):
    """Whether the rule would answer that request, and what it would send (with a sample canary,
    never a real one)."""

    matches: bool
    response: rules.RenderedResponse


def _rule_record(row: queries.ListRulesRow) -> RuleRecord:
    return RuleRecord.model_construct(
        id=row.id_,
        position=row.position,
        updated=row.updated,
        hits=row.hits,
        method=row.method,
        path_pattern=row.path_pattern,
        condition=row.condition,
        status_code=row.status_code,
        content_type=row.content_type,
        headers=rules.headers_from_json(row.headers),
        body=row.body,
        delay_ms=row.delay_ms,
        expires=row.expires,
        note=row.note,
    )


async def _rules(db_conn: DBConn) -> list[RuleRecord]:
    return [_rule_record(row) async for row in queries.list_rules(db_conn)]


@router.get("/rules")
async def list_rules(_admin: CurrentAdmin, db_conn: DBConn) -> list[RuleRecord]:
    """Every rule, in the order they are tried."""
    return await _rules(db_conn)


class Marker(BaseModel):
    name: str
    description: str


# These two come before _RULE, which would take "markers" or "preview" for a rule id
# (test_fixed_paths_reach_their_routes).
@router.get("/rules/markers")
async def list_rule_markers(_admin: CurrentAdmin) -> list[Marker]:
    """What a rule's templates can use."""
    return [Marker(name=name, description=text) for name, text in rules.MARKERS.items()]


@router.post("/rules/preview")
async def preview_rule(
    preview: PreviewRequest, _admin: CurrentAdmin, db_conn: DBConn
) -> Preview:
    """What a rule (saved or not) would answer a request from an address, using everything the
    honeypot knows about that address. Issues no canary and records nothing."""
    rule = preview.rule.rule()
    request = rules.Request(
        method=preview.method.upper(), path=preview.path, query=None, headers={}
    )
    markers = await rules.visitor_context(db_conn, str(preview.ip), request)
    markers[rules.Marker.CANARY] = rules.SAMPLE_CANARY
    try:
        matches = rule.matches_request(request.method, request.path) and rule.holds(
            markers
        )
        response = rule.render(markers)
    except LiquidError as exc:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
    return Preview(matches=matches, response=response)


@router.get(_RULE)
async def get_rule(
    rule_id: RuleId, _admin: CurrentAdmin, db_conn: DBConn
) -> RuleRecord:
    # ponytail: reads every rule to find one; a GetRule query if there are ever hundreds.
    for rule in await _rules(db_conn):
        if rule.id == rule_id:
            return rule
    raise HTTPException(HTTPStatus.NOT_FOUND, _NO_SUCH_RULE)


@router.post("/rules")
async def create_rule(
    form: rules.RuleForm, admin: CurrentAdmin, db_conn: DBConn
) -> NewRule:
    """A new rule, tried after every existing one."""
    async with db_conn.transaction():
        rule_id = await queries.create_rule(
            db_conn,
            method=form.method,
            path_pattern=form.path_pattern,
            condition=form.condition,
            status_code=form.status_code,
            content_type=form.content_type,
            headers=rules.headers_json(form.headers),
            body=form.body,
            delay_ms=form.delay_ms,
            expires=form.expires,
            note=form.note,
            created_by_user_id=admin.user_id,
        )
        if rule_id is None:
            # Unreachable: INSERT ... RETURNING returns the row it inserted.
            raise RuntimeError("Creating a rule returned no row")
        await audit(
            db_conn, admin, AuditAction.RULE_CREATED, details={_RULE_ID: str(rule_id)}
        )
    return NewRule(id=rule_id)


@router.post(_RULE, status_code=HTTPStatus.NO_CONTENT)
async def update_rule(
    rule_id: RuleId, form: rules.RuleForm, admin: CurrentAdmin, db_conn: DBConn
) -> None:
    async with db_conn.transaction():
        updated = await queries.update_rule(
            db_conn,
            id_=rule_id,
            method=form.method,
            path_pattern=form.path_pattern,
            condition=form.condition,
            status_code=form.status_code,
            content_type=form.content_type,
            headers=rules.headers_json(form.headers),
            body=form.body,
            delay_ms=form.delay_ms,
            expires=form.expires,
            note=form.note,
        )
        if updated is None:
            raise HTTPException(HTTPStatus.NOT_FOUND, _NO_SUCH_RULE)
        await audit(
            db_conn, admin, AuditAction.RULE_CHANGED, details={_RULE_ID: str(rule_id)}
        )


@router.post(_RULE + "/move", status_code=HTTPStatus.NO_CONTENT)
async def move_rule(
    rule_id: RuleId, move: Move, admin: CurrentAdmin, db_conn: DBConn
) -> None:
    """Swap a rule with the one before (up) or after it (down): earlier rules are tried first."""
    async with db_conn.transaction():
        order = await _rules(db_conn)
        index = next((i for i, rule in enumerate(order) if rule.id == rule_id), None)
        if index is None:
            raise HTTPException(HTTPStatus.NOT_FOUND, _NO_SUCH_RULE)
        other = index - 1 if move.direction is Direction.UP else index + 1
        if not 0 <= other < len(order):
            return
        order[index], order[other] = order[other], order[index]
        # ponytail: renumbers every rule; fine for the handful an admin writes.
        for position, rule in enumerate(order):
            await queries.set_rule_position(db_conn, id_=rule.id, position=position)
        await audit(
            db_conn,
            admin,
            AuditAction.RULE_CHANGED,
            details={_RULE_ID: str(rule_id), _MOVED: move.direction},
        )


@router.post(_RULE + "/remove", status_code=HTTPStatus.NO_CONTENT)
async def remove_rule(rule_id: RuleId, admin: CurrentAdmin, db_conn: DBConn) -> None:
    """Stop using a rule. It is kept, so the hits it answered still name it."""
    async with db_conn.transaction():
        if await queries.remove_rule(db_conn, id_=rule_id) is None:
            raise HTTPException(HTTPStatus.NOT_FOUND, _NO_SUCH_RULE)
        await audit(
            db_conn, admin, AuditAction.RULE_REMOVED, details={_RULE_ID: str(rule_id)}
        )
