from __future__ import annotations

from functools import lru_cache

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from .config import Settings
from .models import Role, User


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=300)


def _role(value: object) -> Role:
    if isinstance(value, list):
        known = [item for item in value if str(item) in Role._value2member_map_]
        if len(known) != 1:
            raise HTTPException(status_code=403, detail={"code": "INVALID_ROLE", "message": "Token must contain exactly one supported role."})
        value = known[0]
    try:
        return Role(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail={"code": "INVALID_ROLE", "message": "Token role is not supported."}) from exc


def authenticate_request(request: Request, settings: Settings) -> User:
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_REQUIRED", "message": "Bearer authentication is required."}, headers={"WWW-Authenticate": "Bearer"})
    token = token.strip()
    if settings.auth_mode == "demo":
        parts = token.split(":")
        if len(parts) != 3 or parts[0] != "demo" or not parts[1]:
            raise HTTPException(status_code=401, detail={"code": "INVALID_DEMO_TOKEN", "message": "Use demo:<subject>:<ROLE>."})
        role = _role(parts[2])
        subject = parts[1][:255]
        return User(subject=subject, email=subject if "@" in subject else None, name=subject.split("@", 1)[0].replace(".", " ").title(), role=role)

    try:
        unverified = jwt.get_unverified_header(token)
        algorithm = str(unverified.get("alg") or "")
        if algorithm != settings.auth_algorithm:
            raise jwt.InvalidAlgorithmError("unexpected token algorithm")
        signing_key = _jwks_client(settings.auth_jwks_url).get_signing_key_from_jwt(token).key
        payload = jwt.decode(token, signing_key, algorithms=[settings.auth_algorithm], audience=settings.auth_audience, issuer=settings.auth_issuer, options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "Bearer token could not be verified."}, headers={"WWW-Authenticate": "Bearer"}) from exc
    role_value = payload.get("role") if payload.get("role") is not None else payload.get("roles")
    return User(subject=str(payload["sub"]), email=str(payload["email"]) if payload.get("email") else None, name=str(payload.get("name") or payload.get("email") or payload["sub"]), role=_role(role_value))


def require_roles(user: User, allowed: set[Role]) -> User:
    if user.role not in allowed:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Your role is not authorized for this action."})
    return user
