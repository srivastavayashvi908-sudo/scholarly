from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from ..auth import check_password, current_user, hash_password, make_token
from ..db import get_conn
from ..models import LoginIn, RegisterIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: RegisterIn, conn=Depends(get_conn)):
    try:
        user = conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (lower(%s), %s, %s) RETURNING id, email, name",
            (body.email, body.name, hash_password(body.password)),
        ).fetchone()
    except UniqueViolation:
        raise HTTPException(409, "An account with that email already exists")
    return {"token": make_token(user["id"]), "user": user}


@router.post("/login")
def login(body: LoginIn, conn=Depends(get_conn)):
    user = conn.execute(
        "SELECT id, email, name, password_hash FROM users WHERE email = lower(%s)", (body.email,)
    ).fetchone()
    if user is None or not check_password(body.password, user.pop("password_hash")):
        raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(user["id"]), "user": user}


@router.get("/me")
def me(user=Depends(current_user)):
    return user
