
from datetime import datetime
from enum import Enum, IntFlag, auto
import json
from typing import Any

from sqlalchemy import Table, Column, Integer, String, Text, LargeBinary, DateTime, ForeignKey, Index, func, inspect, select, insert
from sqlalchemy.orm import relationship, ColumnProperty, RelationshipProperty
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import async_object_session
from sqlalchemy.ext.compiler import compiles
from sqlalchemy_fulltext import FullText
from sqlalchemy_utils import ChoiceType

__all__ = [
    'Base',
    'User',
    'File',
    'Note',
]

Base = declarative_base()

class User(Base):
    __tablename__ = 'user'
    
    id = Column(Text, primary_key=True)
    
    username = Column(Text)
    name = Column(Text)
    avatar_url = Column(Text)
    
    is_following = Column(Integer)
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class File(Base):
    __tablename__ = 'file'
    
    id = Column(Text, primary_key=True)
    
    name = Column(Text)
    # mime type
    type = Column(Text)
    
    url = Column(Text)
    thumbnail_url = Column(Text)
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

note_files = Table('note_file', Base.metadata,
    Column('note_id', Text, ForeignKey('note.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('file_id', Text, ForeignKey('file.id', ondelete='CASCADE'), nullable=False)
)

class Note(Base):
    __tablename__ = 'note'
    
    id = Column(Text, primary_key=True)
    
    user_id = Column(Text, ForeignKey('user.id'), nullable=False)
    renote_id = Column(Text, ForeignKey('note.id'), nullable=True)
    
    cw = Column(Text)
    text = Column(Text)
    
    renote_count = Column(Integer)
    react_count = Column(Integer)
    note_time = Column(DateTime)
    
    # store own reaction, base on own user id (hide notes with reactions lol)
    reaction = Column(Text)
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    user = relationship('User')
    renote = relationship('Note', remote_side=[id])
    files = relationship('File', secondary=note_files)

