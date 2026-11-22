"""Demo CRM servisi: örnek test senaryolarının koştuğu küçük bir API (ATOP-52).

Gerçek bir sisteme dokunmadan platformu denemek için. Veriler bellekte tutulur; servis
yeniden başlayınca (ya da POST /reset ile) sıfırlanır.

Docker içinde: http://demo:8001   ·   Tarayıcıdan: http://localhost:8001/docs

Kullanıcı: demo / demo123

Uç noktalar:
    POST /auth/login                giriş, token döner (yanlış şifre: 401)
    GET  /companies                 şirket listesi                      (token gerekli)
    POST /leads                     lead (potansiyel müşteri) oluştur    (aynı e-posta: 409)
    GET  /leads/{id}                lead detayı                          (yoksa: 404)
    POST /offers                    lead için teklif oluştur             (tutar <= 0: 422)
    GET  /companies/{id}/offers     şirketin teklifleri
    POST /reset                     tüm lead ve teklifleri sil
"""

import secrets
from datetime import UTC, datetime
from threading import Lock
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

DEMO_USER = "demo"
DEMO_PASSWORD = "demo123"
COMPANIES = [
    {"id": 1, "name": "Anadolu Lojistik A.Ş.", "city": "İstanbul"},
    {"id": 2, "name": "Ege Gıda Ltd.", "city": "İzmir"},
    {"id": 3, "name": "Başkent Yazılım A.Ş.", "city": "Ankara"},
]

app = FastAPI(
    title="Demo CRM API",
    version="1.0.0",
    description="API Test Platformu'nun örnek senaryoları için demo servis. "
    f"Kullanıcı: `{DEMO_USER}` / `{DEMO_PASSWORD}`",
)


class Store:
    def __init__(self) -> None:
        self.lock = Lock()
        self.reset()

    def reset(self) -> None:
        self.tokens: set[str] = set()
        self.leads: dict[int, dict] = {}
        self.offers: dict[int, dict] = {}
        self.next_lead = 1
        self.next_offer = 1


store = Store()
bearer = HTTPBearer(auto_error=False)


def current_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None or credentials.credentials not in store.tokens:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Geçerli bir token gerekli",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


Authorized = Annotated[str, Depends(current_token)]


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = 3600


class LeadCreate(BaseModel):
    company_id: int
    contact_name: str = Field(min_length=1, max_length=100)
    email: EmailStr


class OfferCreate(BaseModel):
    lead_id: int
    amount: float = Field(gt=0, description="Teklif tutarı, sıfırdan büyük")
    currency: Literal["TRY", "USD", "EUR"] = "TRY"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "Demo CRM API", "docs": "/docs"}


@app.post("/auth/login", response_model=LoginResponse, tags=["Kimlik"])
def login(body: LoginRequest) -> LoginResponse:
    if body.username != DEMO_USER or body.password != DEMO_PASSWORD:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Kullanıcı adı veya şifre hatalı")
    token = secrets.token_urlsafe(24)
    with store.lock:
        store.tokens.add(token)
    return LoginResponse(access_token=token)


@app.get("/companies", tags=["Şirketler"])
def list_companies(_: Authorized) -> list[dict]:
    return COMPANIES


def _company(company_id: int) -> dict:
    company = next((item for item in COMPANIES if item["id"] == company_id), None)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Şirket bulunamadı")
    return company


@app.post("/leads", status_code=status.HTTP_201_CREATED, tags=["Lead"])
def create_lead(body: LeadCreate, _: Authorized) -> dict:
    company = _company(body.company_id)
    email = body.email.lower()
    with store.lock:
        if any(lead["email"] == email for lead in store.leads.values()):
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail=f"Bu e-posta ile lead zaten var: {email}"
            )
        lead = {
            "id": store.next_lead,
            "company_id": company["id"],
            "company_name": company["name"],
            "contact_name": body.contact_name,
            "email": email,
            "status": "new",
            "created_at": _now(),
        }
        store.leads[lead["id"]] = lead
        store.next_lead += 1
    return lead


@app.get("/leads/{lead_id}", tags=["Lead"])
def get_lead(lead_id: int, _: Authorized) -> dict:
    lead = store.leads.get(lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Lead bulunamadı")
    return lead


@app.post("/offers", status_code=status.HTTP_201_CREATED, tags=["Teklif"])
def create_offer(body: OfferCreate, _: Authorized) -> dict:
    with store.lock:
        lead = store.leads.get(body.lead_id)
        if lead is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Lead bulunamadı")
        offer = {
            "id": store.next_offer,
            "lead_id": lead["id"],
            "company_id": lead["company_id"],
            "amount": body.amount,
            "currency": body.currency,
            "status": "draft",
            "created_at": _now(),
        }
        store.offers[offer["id"]] = offer
        store.next_offer += 1
        lead["status"] = "offered"
    return offer


@app.get("/companies/{company_id}/offers", tags=["Teklif"])
def company_offers(company_id: int, _: Authorized) -> list[dict]:
    _company(company_id)
    return [offer for offer in store.offers.values() if offer["company_id"] == company_id]


@app.post("/reset", tags=["Yönetim"])
def reset(_: Authorized) -> dict[str, str]:
    with store.lock:
        tokens = store.tokens
        store.reset()
        store.tokens = tokens  # oturumlar kalsın
    return {"message": "Lead ve teklifler silindi"}
