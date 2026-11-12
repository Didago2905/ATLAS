"""Explicit file-bound production capability. Never creates files or receipt schema."""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, AwareDatetime

from app.editorial.candidate_lookup import _sqlite_file


class FileTarget(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    path: str
    device: int = Field(strict=True, ge=0)
    inode: int = Field(strict=True, gt=0)


class ProductionExecutionConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    enabled: StrictBool = False
    activation_id: UUID | None = None
    not_before: AwareDatetime | None = None
    editorial: FileTarget | None = None
    catalog: FileTarget | None = None


_SEAL = object()


@dataclass(frozen=True)
class ProductionExecutionScope:
    editorial_engine: object = field(repr=False)
    catalog_engine: object = field(repr=False)
    allowlist: tuple = field(repr=False)
    activation_id: str
    not_before: datetime
    seal: object = field(default=None, repr=False)


def _identity(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_file():
        raise ValueError('canonical_execution_file_required')
    repo = Path(__file__).resolve().parents[2]
    if any(public == path or public in path.parents for public in (repo/'static', repo/'frontend', repo/'build')):
        raise ValueError('public_execution_storage_rejected')
    stat = path.stat()
    if stat.st_nlink != 1:
        raise ValueError('hardlinked_execution_target')
    return str(path), stat.st_dev, stat.st_ino


def allow_production_execution(editorial_engine, catalog_engine, *, config):
    config = ProductionExecutionConfig.model_validate(config)
    if not config.enabled:
        raise ValueError('production_execution_disabled')
    if not config.activation_id or not config.not_before or not config.editorial or not config.catalog:
        raise ValueError('complete_production_allowlist_required')
    configured = tuple((item.path, item.device, item.inode) for item in (config.editorial, config.catalog))
    scope = ProductionExecutionScope(editorial_engine, catalog_engine, configured,
                                     str(config.activation_id), config.not_before, _SEAL)
    validate_production_scope(scope)
    return scope


def validate_production_scope(scope, *, catalog_engine=None, editorial_database=None):
    if type(scope) is not ProductionExecutionScope or scope.seal is not _SEAL:
        raise ValueError('production_execution_disabled')
    identities = tuple(_identity(_sqlite_file(str(engine.url))) for engine in (scope.editorial_engine, scope.catalog_engine))
    if identities != scope.allowlist or identities[0][1:] == identities[1][1:]:
        raise ValueError('execution_target_not_allowlisted')
    if catalog_engine is not None and catalog_engine is not scope.catalog_engine:
        raise ValueError('execution_engine_mismatch')
    if editorial_database is not None and _identity(editorial_database) != identities[0]:
        raise ValueError('execution_source_mismatch')


def validate_request(scope, request):
    if request.get('production_activation') != scope.activation_id \
            or datetime.fromisoformat(request['approved_at']) < scope.not_before:
        raise ValueError('historical_execution_request_rejected')


def activation(scope):
    if type(scope) is ProductionExecutionScope:
        validate_production_scope(scope)
        return scope.activation_id
    return None
