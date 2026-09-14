import os
import json
import base64
import hmac
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_db
from bson import ObjectId

SECRET_KEY = os.environ.get("JWT_SECRET", "careseva_super_secure_jwt_secret_key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)

def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def _base64url_decode(data: str) -> bytes:
    padding = '=' * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data + padding)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({"exp": int(expire.timestamp()), "iat": int(now.timestamp())})
    
    header = {"alg": ALGORITHM, "typ": "JWT"}
    header_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
    payload_json = json.dumps(to_encode, separators=(',', ':')).encode('utf-8')
    
    encoded_header = _base64url_encode(header_json)
    encoded_payload = _base64url_encode(payload_json)
    
    signing_input = f"{encoded_header}.{encoded_payload}".encode('utf-8')
    signature = hmac.new(SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
    encoded_signature = _base64url_encode(signature)
    
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"

def decode_access_token(token: str) -> Optional[dict]:
    try:
        parts = token.strip().split('.')
        if len(parts) != 3:
            return None
        
        encoded_header, encoded_payload, encoded_signature = parts
        signing_input = f"{encoded_header}.{encoded_payload}".encode('utf-8')
        expected_sig = hmac.new(SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
        actual_sig = _base64url_decode(encoded_signature)
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        
        payload_bytes = _base64url_decode(encoded_payload)
        payload = json.loads(payload_bytes.decode('utf-8'))
        
        exp = payload.get("exp")
        if exp and int(datetime.now(timezone.utc).timestamp()) > exp:
            return None
            
        return payload
    except Exception:
        return None

def clean_phone_number(phone_str: str) -> str:
    clean_p = phone_str.strip().replace(" ", "").replace("-", "")
    if clean_p.startswith("+91"):
        clean_p = clean_p[3:]
    elif clean_p.startswith("91") and len(clean_p) == 12:
        clean_p = clean_p[2:]
    return clean_p

async def get_optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_patient_phone: Optional[str] = Header(None, alias="X-Patient-Phone"),
    db = Depends(get_db)
) -> Optional[Dict[str, Any]]:
    # 1. Try Bearer token in Authorization header
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "authorization" in request.headers:
        auth_hdr = request.headers["authorization"]
        if auth_hdr.lower().startswith("bearer "):
            token = auth_hdr[7:].strip()
            
    if token:
        payload = decode_access_token(token)
        if payload:
            user_id = payload.get("sub") or payload.get("id") or payload.get("user_id")
            phone = payload.get("phone")
            pid = payload.get("pid")
            
            user = None
            if user_id:
                try:
                    user = await db["users"].find_one({"_id": ObjectId(user_id)})
                except Exception:
                    user = await db["users"].find_one({"_id": user_id})
            if not user and phone:
                user = await db["users"].find_one({"phone": clean_phone_number(phone)})
            if not user and pid:
                user = await db["users"].find_one({"pid": pid})
                
            if user:
                return {
                    "id": str(user["_id"]),
                    "name": user.get("name", "Registered Patient"),
                    "email": user.get("email"),
                    "phone": user.get("phone", clean_phone_number(phone) if phone else ""),
                    "pid": user.get("pid"),
                    "role": user.get("role", "patient"),
                    "hospital_id": user.get("hospital_id")
                }
            elif user_id or phone:
                return {
                    "id": str(user_id or "unspecified"),
                    "name": payload.get("name", "Registered Patient"),
                    "email": payload.get("email"),
                    "phone": clean_phone_number(phone) if phone else "",
                    "pid": pid,
                    "role": payload.get("role", "patient"),
                    "hospital_id": payload.get("hospital_id")
                }

    # 2. Fallback to authenticated headers
    if x_user_id:
        user = None
        try:
            user = await db["users"].find_one({"_id": ObjectId(x_user_id)})
        except Exception:
            user = await db["users"].find_one({"_id": x_user_id})
        if user:
            return {
                "id": str(user["_id"]),
                "name": user.get("name"),
                "email": user.get("email"),
                "phone": user.get("phone", ""),
                "pid": user.get("pid"),
                "role": user.get("role", "patient"),
                "hospital_id": user.get("hospital_id")
            }

    if x_patient_phone:
        clean_p = clean_phone_number(x_patient_phone)
        user = await db["users"].find_one({"phone": clean_p})
        if user:
            return {
                "id": str(user["_id"]),
                "name": user.get("name"),
                "email": user.get("email"),
                "phone": clean_p,
                "pid": user.get("pid"),
                "role": user.get("role", "patient"),
                "hospital_id": user.get("hospital_id")
            }

    return None

async def get_current_user(
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> Dict[str, Any]:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token missing or invalid. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user
