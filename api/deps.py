import json
import logging
import httpx
from typing import Dict, Any

from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwcrypto import jwk, jwe
from jwcrypto.common import base64url_encode

from core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

security = HTTPBearer()

def get_jwk() -> jwk.JWK:
    # Key is expected to be 16 bytes for A128GCM.
    key_str = settings.jwt_key or "portgas d. asxce"
    key_bytes = key_str.encode('utf-8')
    encoded_key = base64url_encode(key_bytes)
    return jwk.JWK(kty='oct', k=encoded_key)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Extracts and decrypts the JWE token from Authorization header.
    Returns the claims.
    """
    token = credentials.credentials
    key = get_jwk()
    
    try:
        jwe_token = jwe.JWE()
        jwe_token.deserialize(token)
        jwe_token.decrypt(key)
        payload = jwe_token.payload
        
        claims = json.loads(payload.decode('utf-8'))
        
        # Verify expiration
        import time
        now = int(time.time())
        if 'exp' in claims and claims['exp'] < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is expired"
            )
            
        return claims
    except Exception as e:
        logger.error(f"JWT Decryption error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You are not authorized or invalid token"
        )


class RoleChecker:
    def __init__(self, path_master: str, action: str):
        """
        action: 'view', 'create', 'update', 'delete', 'detail', 'etc'
        """
        self.path_master = path_master
        self.action = action

    async def __call__(self, request: Request, user: Dict[str, Any] = Depends(get_current_user)):
        """
        Calls external API Role to verify if user has permission.
        """
        role_name = user.get("role", "")
        logger.info(f"Role Name: {role_name}")
        req_data = {
            "role_name": role_name,
            "path": self.path_master
        }
        logger.info(f"Request Data: {req_data}")
        
        auth_header = request.headers.get("Authorization")
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.api_role_url}/verify",
                    json=req_data,
                    headers={"Authorization": auth_header},
                    timeout=30.0
                )
                
            if resp.status_code > 201:
                logger.warning(f"Role Verify Failed: {resp.status_code} - {resp.text}")
                raise HTTPException(status_code=403, detail="Forbidden")
                
            result_api = resp.json()
            data = result_api.get("data", {})
            
            if self.action == "view" and not data.get("view", False):
                raise HTTPException(status_code=403, detail="Forbidden: Missing 'view' permission")
            # elif self.action == "etc" and not data.get("etc", False):
            #     raise HTTPException(status_code=403, detail="Forbidden: Missing 'etc' permission")
            # Can add other actions as needed
            
        except httpx.RequestError as e:
            logger.error(f"API Role request failed: {str(e)}")
            raise HTTPException(status_code=403, detail="Forbidden (Role Verify Service Error)")
            
        return user
