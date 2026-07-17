from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    full_name: str
    phone_number: str = Field(..., examples=["+2207123456"])
    email: EmailStr | None = None
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    phone_number: str
    password: str


class UserOut(BaseModel):
    id: str
    full_name: str
    phone_number: str
    email: EmailStr | None
    egov_verified: bool
    tapsign_enrolled: bool

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
