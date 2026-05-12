from decimal import Decimal, InvalidOperation

import httpx

from app.core.config import Settings, get_settings
from app.schemas.portfolio import CashBalance


class WalletClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def get_cash_balance(self, user_id: str) -> CashBalance:
        if not self.settings.wallet_service_url:
            return CashBalance()

        url = f"{self.settings.wallet_service_url.rstrip('/')}/internal/wallet/{user_id}/balance"
        try:
            async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError:
            return CashBalance()

        return self._parse_cash_balance(data)

    def _parse_cash_balance(self, data: dict) -> CashBalance:
        payload = data.get("cash") if isinstance(data.get("cash"), dict) else data
        return CashBalance(
            currency=str(payload.get("currency", "USD")),
            available=self._decimal_from_any(
                payload.get("available")
                or payload.get("available_cash")
                or payload.get("balance")
                or Decimal("0"),
            ),
            reserved=self._decimal_from_any(
                payload.get("reserved")
                or payload.get("reserved_cash")
                or payload.get("hold")
                or Decimal("0"),
            ),
        )

    def _decimal_from_any(self, value: object) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal("0")
