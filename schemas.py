from pydantic import BaseModel, Field
from typing import Optional, Any, Union
from datetime import datetime
from enum import Enum


class MessageHeader(BaseModel):
    c: str



class DownloadType(Enum):
    Post = 1
    Subscription = 2

class ParseResponse(BaseModel):
    plugin: str
    source: str
    type: DownloadType
    id: str | None
    options: Any | None


import hoordu.models as m
from sqlalchemy import inspect
from sqlalchemy.orm.collections import InstrumentedList

class BuildContext:
    def __init__(self, parent=None):
        self.parent = parent
        if self.parent is not None:
            self._refs = self.parent._refs.copy()
        else:
            self._refs = set()
    
    def push(self):
        return BuildContext(self)
    
    def pop(self):
        return self.parent
    
    def check(self, v):
        if not hasattr(v, '__table__'):
            return True
        
        ins = inspect(v.__class__)
        key = []
        for pk in ins.primary_key:
            k = next((attr for attr in ins.c.keys() if ins.c[attr].name == pk.name), None)
            key.append(getattr(v, k))
        
        ref = (type(v), tuple(key))
        if ref in self._refs:
            return False
        
        self._refs.add(ref)
        return True


class Models:
    def __init__(self):
        self.models = {}
        self.converters = {}
        
        self._register_converter(list, self._conv_list)
        self._register_converter(InstrumentedList, self._conv_list)
        self._register_converter(dict, self._conv_dict)
    
    def _conv_list(self, l, ctx):
        r = []
        for v in l:
            rv = self.build(v, ctx.push())
            if rv is not None:
                r.append(rv)
        
        return r
    
    def _conv_dict(self, d, ctx):
        r = []
        for k, v  in d.items():
            rv = self.build(v, ctx.push())
            if rv is not None:
                r[k] = rv
        
        return r
    
    def register(self, SQLModel):
        def reg_internal(PYDModel):
            self.models[SQLModel] = PYDModel
            return PYDModel
        return reg_internal
    
    def _register_converter(self, type, converter):
        self.converters[type] = converter
    
    def register_converter(self, Type):
        def reg_conv_internal(func):
            self._register_converter(Type, func)
            return func
        return reg_conv_internal
    
    def build(self, obj, ctx=None):
        if ctx is None:
            ctx = BuildContext()
        
        conv = self.converters.get(type(obj))
        if conv is not None:
            obj = conv(obj, ctx)
        
        target = self.models.get(type(obj))
        if target is not None:
            ctx.check(obj)
            d = {k: self.build(v, ctx.push()) for k, v in obj.__dict__.items() if not k.startswith('_') and ctx.check(v)}
            return target(**d)
            
        else:
            return obj


models = Models()

@models.register(m.Source)
class Source(BaseModel):
    id: int
    name: str
    config: str | None
    metadata: str | None = Field(alias='metadata_')
    
    preferred_plugin: Union['Plugin', None]
    
    class Config:
        allow_population_by_field_name = True

@models.register(m.Subscription)
class Subscription(BaseModel):
    id: int | None
    repr: str | None
    name: str
    options: str | None
    
    enabled: bool | None
    metadata: str | None = Field(alias='metadata_')
    
    source_id: int | None
    source: Source | None
    plugin_id: int | None
    plugin: Union['Plugin', None]
    
    class Config:
        allow_population_by_field_name = True


@models.register(m.Plugin)
class Plugin(BaseModel):
    id: int
    name: str
    source_id: int
    source: Source | None

@models.register(m.File)
class File(BaseModel):
    id: int
    local_id: int | None
    local_order: int | None
    remote_id: int | None
    remote_order: int | None
    
    source_url: str | None
    
    file_url: str | None
    thumb_url: str | None
    
    hash: str | None
    filename: str | None
    mime: str | None
    
    metadata: str | None = Field(alias='metadata_')
    
    class Config:
        allow_population_by_field_name = True
    

@models.register(m.Post)
@models.register(m.RemotePost)
class Post(BaseModel):
    id: int
    source_id: int
    source: Source | None
    
    original_id: str | None
    url: str | None
    
    files: list[File]
    
    title: str | None
    comment: str | None
    post_time: datetime | None
    
    type: m.PostType
    metadata: str | None = Field(alias='metadata_')
    
    related: list['Post'] | None
    
    """
    favorite: bool
    hidden: bool
    removed: bool
    """
    
    class Config:
        allow_population_by_field_name = True

@models.register(m.FeedEntry)
class FeedEntry(BaseModel):
    subscription_id: int
    subscription: Source | None
    
    remote_post_id: int
    post: Post | None
    
    sort_index: str

@models.register(m.Related)
class Related(BaseModel):
    post: Post | None = Field(alias='remote')
    
    class Config:
        allow_population_by_field_name = True


Source.update_forward_refs()
Subscription.update_forward_refs()
Post.update_forward_refs()


