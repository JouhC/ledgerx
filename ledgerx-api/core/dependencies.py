from fastapi import FastAPI, HTTPException, Depends, Request, Query


def auth_user(request: Request):
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Bearer "): raise HTTPException(401, "Missing token")
    token = auth.split(" ",1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        uid = payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid token")
    # naive: reverse index by user_id
    u = next((u for u in USERS.values() if u["id"]==uid), None)
    if not u: raise HTTPException(401, "User not found")
    return u