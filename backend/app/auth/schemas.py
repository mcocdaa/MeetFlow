from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=200)

    @field_validator("username", "display_name")
    @classmethod
    def identity_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class PasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)


class AdminCreateUserRequest(RegisterRequest):
    pass


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=12, max_length=200)


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_color: str
    role: str
    status: str
