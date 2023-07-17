from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class User(BaseModel):
    id: str
    username: str
    name: str | None
    avatar_url: str | None
    is_following: bool
    
    class Config:
        orm_mode = True

class File(BaseModel):
    id: str
    name: str
    url: str
    thumbnail_url: str
    
    class Config:
        orm_mode = True

class Note(BaseModel):
    id: str
    user: User
    renote: Optional['Note']
    files: list[File] = []
    
    cw: str | None = None
    text: str | None = None
    
    renote_count: str | None = None
    react_count: str | None = None
    note_time: datetime
    
    reaction: str | None = None
    
    class Config:
        orm_mode = True
