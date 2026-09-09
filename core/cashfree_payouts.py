import httpx
import uuid
import time
from typing import Optional, Dict, Any
from core.config import settings

class CashfreePayoutsClient:
    def __init__(self):
        self._auth_token: Optional[str] = None
        self._token_expires_at: float = 0

    def get_base_url(self) -> str:
        env = (settings.CASHFREE_PAYOUT_ENV or settings.CASHFREE_ENV or "PRODUCTION").upper()
        if env in ["PRODUCTION", "PROD"]:
            return "https://payout-api.cashfree.com/payout/v1"
        return "https://payout-gamma.cashfree.com/payout/v1"

    def _get_client_id(self) -> str:
        return settings.CASHFREE_PAYOUT_CLIENT_ID or settings.CASHFREE_APP_ID or ""

    def _get_client_secret(self) -> str:
        return settings.CASHFREE_PAYOUT_CLIENT_SECRET or settings.CASHFREE_SECRET_KEY or ""

    def is_configured(self) -> bool:
        cid = self._get_client_id()
        csec = self._get_client_secret()
        return bool(cid and csec and not cid.startswith("TEST_") and cid != "YOUR_CASHFREE_APP_ID")

    async def get_auth_token(self) -> Optional[str]:
        """
        Retrieves or refreshes Bearer Auth Token from Cashfree Payouts API.
        """
        now = time.time()
        if self._auth_token and self._token_expires_at > now + 60:
            return self._auth_token

        if not self.is_configured():
            return "SIMULATED_BEARER_TOKEN"

        url = f"{self.get_base_url()}/authorize"
        headers = {
            "X-Client-Id": self._get_client_id(),
            "X-Client-Secret": self._get_client_secret(),
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "SUCCESS" and "data" in data:
                        token = data["data"].get("token")
                        expiry = data["data"].get("expiry", 3600)
                        self._auth_token = token
                        self._token_expires_at = now + float(expiry)
                        return token
                    else:
                        print(f"[Cashfree Payout Auth]: {data.get('message')}")
                else:
                    print(f"[Cashfree Payout Auth HTTP {resp.status_code}]: {resp.text}")
        except Exception as e:
            print(f"[Cashfree Payout Auth Network Error]: {e}")

        return None

    async def add_beneficiary(
        self,
        bene_id: str,
        name: str,
        email: str,
        phone: str,
        bank_account: Optional[str] = None,
        ifsc: Optional[str] = None,
        vpa: Optional[str] = None,
        address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registers or updates a hospital as a Beneficiary on Cashfree Payouts.
        """
        token = await self.get_auth_token()
        clean_phone = "".join(filter(str.isdigit, str(phone)))[-10:] if phone else "9999999999"

        payload = {
            "beneId": bene_id,
            "name": name,
            "email": email or "hospital@careseva.in",
            "phone": clean_phone,
            "address1": address or "Healthcare Facility, India"
        }

        if bank_account and ifsc:
            payload["bankAccount"] = bank_account.strip()
            payload["ifsc"] = ifsc.strip().upper()
        if vpa:
            payload["vpa"] = vpa.strip()

        if not token or token == "SIMULATED_BEARER_TOKEN":
            return {
                "status": "SUCCESS",
                "subCode": "200",
                "message": "Beneficiary registered (Simulated Sandbox Mode)",
                "beneId": bene_id,
                "is_simulated": True
            }

        url = f"{self.get_base_url()}/addBeneficiary"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                data = resp.json()
                # Status 409 or subCode 409 usually means beneficiary already exists
                if resp.status_code in [200, 201] or data.get("subCode") in ["200", "409", "400"]:
                    return data
                return {
                    "status": "ERROR",
                    "code": resp.status_code,
                    "message": data.get("message", resp.text)
                }
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    async def request_transfer(
        self,
        transfer_id: str,
        bene_id: str,
        amount: float,
        remarks: Optional[str] = "CareSeva Hospital Settlement",
        transfer_mode: str = "banktransfer"
    ) -> Dict[str, Any]:
        """
        Initiates a direct transfer / payout to the registered hospital beneficiary.
        """
        token = await self.get_auth_token()
        clean_amount = f"{round(float(amount), 2):.2f}"

        payload = {
            "beneId": bene_id,
            "amount": clean_amount,
            "transferId": transfer_id,
            "transferMode": transfer_mode.lower(), # "banktransfer" or "upi"
            "remarks": remarks
        }

        if not token or token == "SIMULATED_BEARER_TOKEN":
            # Sandbox simulation
            simulated_utr = f"UTR{int(time.time())}{uuid.uuid4().hex[:6].upper()}"
            return {
                "status": "SUCCESS",
                "subCode": "200",
                "message": "Payout transfer simulated successfully",
                "data": {
                    "referenceId": f"CF_REF_{uuid.uuid4().hex[:8].upper()}",
                    "utr": simulated_utr,
                    "transferId": transfer_id,
                    "amount": clean_amount,
                    "status": "SUCCESS"
                },
                "is_simulated": True
            }

        url = f"{self.get_base_url()}/requestTransfer"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                data = resp.json()
                return data
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    async def get_transfer_status(self, transfer_id: str) -> Dict[str, Any]:
        """
        Queries status of an existing transfer ID from Cashfree Payouts.
        """
        token = await self.get_auth_token()
        if not token or token == "SIMULATED_BEARER_TOKEN":
            return {
                "status": "SUCCESS",
                "data": {
                    "transfer": {
                        "transferId": transfer_id,
                        "status": "SUCCESS",
                        "utr": f"UTR_SIM_{transfer_id}"
                    }
                },
                "is_simulated": True
            }

        url = f"{self.get_base_url()}/getTransferStatus?transferId={transfer_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                return resp.json()
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    async def get_wallet_balance(self) -> Dict[str, Any]:
        """
        Fetches current available Cashfree Payouts balance.
        """
        token = await self.get_auth_token()
        if not token or token == "SIMULATED_BEARER_TOKEN":
            return {
                "status": "SUCCESS",
                "data": {
                    "balance": 50000.0,
                    "availableBalance": 50000.0,
                    "currency": "INR"
                },
                "is_simulated": True
            }

        url = f"{self.get_base_url()}/getBalance"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                return resp.json()
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

payouts_client = CashfreePayoutsClient()
