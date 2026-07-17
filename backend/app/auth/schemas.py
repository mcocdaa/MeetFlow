from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=200)


class PasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=200)


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=12, max_length=200)


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    status: str
