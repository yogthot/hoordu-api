#!/usr/bin/env python

import uvloop
uvloop.install()

import asyncio
import contextlib
from datetime import datetime, timedelta
from functools import partial
import pathlib

from fastapi import FastAPI, APIRouter, WebSocket, Body, Depends, HTTPException, WebSocketException
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, Response
from starlette.websockets import WebSocketDisconnect

import hoordu
from hoordu.models import *
from hoordu.forms import *
from sqlalchemy import cast, Numeric
from sqlalchemy.orm import selectinload
import sqlalchemy.exc as sqlexc


import schemas as s
from context import ContextSessionDepedency, session
from typing import Optional, Any


from sqlalchemy import Table, Column, Integer, String, Text, LargeBinary, DateTime, Numeric, ForeignKey, Index, func, inspect, select, insert
from sqlalchemy.orm import relationship, ColumnProperty, RelationshipProperty
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import async_object_session
from sqlalchemy.ext.compiler import compiles
from sqlalchemy_fulltext import FullText
from sqlalchemy_utils import ChoiceType


class Gallery(Base):
    __tablename__ = 'gallery'

    id = Column(Integer, primary_key=True)
    name = Column(Text)
    post_id = Column(Integer, ForeignKey('remote_post.id', ondelete='CASCADE'))

    post = relationship('RemotePost')




def create_api(hrd: hoordu.hoordu) -> APIRouter:
    api = APIRouter(
        dependencies=[Depends(ContextSessionDepedency(hrd))]
    )
    api.get = partial(api.get, response_model_exclude_unset=True, response_model_by_alias=False)
    api.post = partial(api.post, response_model_exclude_unset=True, response_model_by_alias=False)
    api.put = partial(api.put, response_model_exclude_unset=True, response_model_by_alias=False)
    api.delete = partial(api.delete, response_model_exclude_unset=True, response_model_by_alias=False)
    
    # TODO get the type automatically?
    @s.models.register_converter(File)
    def convert_file(file: File, ctx) -> s.File:
        orig, thumb = hrd.get_file_paths(file)
        
        def convert_url(url):
            url = pathlib.Path(url)
            
            if not url.exists():
                return None
            
            base = pathlib.Path(hrd.config.settings.base_path)
            return str(pathlib.Path('/data') / url.relative_to(base))
        
        orig = convert_url(orig)
        thumb = convert_url(thumb)
        
        hash = file.hash.hex() if file.hash is not None else None
        
        return s.File(
            id=file.id,
            
            local_id=file.local_id,
            local_order=file.local_order,
            remote_id=file.remote_id,
            remote_order=file.remote_order,
            
            file_url=orig,
            thumb_url=thumb,
            
            hash=hash,
            filename=file.filename,
            
            mime=file.mime,
            metadata=file.metadata_,
            remote_identifier=file.remote_identifier,
        )
    
    @s.models.register_converter(Related)
    def convert_related(related: Related, ctx) -> s.Post:
        if related.remote is not None:
            return s.models.build(related.remote)
        else:
            return None
    
    @s.models.register_converter(FormEntry)
    def convert_entry(entry: FormEntry, ctx) -> s.Entry:
        return s.Entry(
            id=entry.id,
            type=type(entry).__name__,
            label=entry.label,
            value=entry.value,
        )
    
    @api.get('/parse')
    async def parse(url: str) -> list[s.ParseResponse]:
        parsed = await hrd.parse_url(url)
        l = []
        for p, o in parsed:
            dl_type = s.DownloadType.Post
            if isinstance(o, hoordu.Dynamic):
                dl_type = s.DownloadType.Subscription
            
            r = s.ParseResponse(
                plugin=p.id,
                source=p.name,
                type=dl_type
            )
            if isinstance(o, hoordu.Dynamic):
                r.options = o
                
            else:
                r.id = o
            
            l.append(r)
        
        return l
    
    @api.get('/sources')
    async def list_sources() -> list[s.Source]:
        sources = await session.select(Source) \
                .options(
                    selectinload(Source.preferred_plugin),
                ) \
                .all()
        
        return s.models.build(sources)
    
    @api.get('/source/{source_name}')
    async def get_source(source_name: str) -> s.Source:
        source = await session.select(Source) \
                .where(Source.name == source_name) \
                .options(
                    selectinload(Source.preferred_plugin),
                ) \
                .one_or_none()
        
        if source is None:
            raise HTTPException(status_code=404, detail=f'Source "{source_name}" not found')
        
        return s.models.build(source)
    
    @api.get('/source/{source_name}/subscriptions')
    async def list_source_subscriptions(source_name: str) -> list[s.Subscription]:
        source = await session.select(Source) \
                .where(Source.name == source_name) \
                .one_or_none()
        
        if source is None:
            raise HTTPException(status_code=404, detail=f'Source "{source_name}" not found')
        
        subscriptions = await session.select(Subscription) \
                .where(Subscription.source_id == source.id) \
                .options(
                    selectinload(Subscription.source),
                ) \
                .all()
        
        return s.models.build(subscriptions)
    
    @api.post('/source/{source_name}/subscriptions')
    async def create_subscription(source_name: str, subscription: s.Subscription) -> s.Subscription:
        source = await session.select(Source) \
                .where(Source.name == source_name) \
                .one_or_none()
        
        if source is None:
            raise HTTPException(status_code=404, detail=f'Source "{source_name}" not found')
        
        sub = Subscription(
            source=source,
            name=subscription.name,
            options=subscription.options,
            metadata_=subscription.metadata
        )
        
        if subscription.plugin_id is not None:
            sub.plugin_id = subscription.plugin_id
        else:
            sub.plugin_id = source.preferred_plugin_id
        
        try:
            session.add(sub)
            await session.commit()
            
        except sqlexc.IntegrityError:
            raise HTTPException(status_code=409)
        
        return s.models.build(sub)
    
    @api.get('/source/{source_name}/subscription/{subscription_name}')
    async def get_subscription(source_name: str, subscription_name: str) -> s.Subscription:
        source = await session.select(Source) \
                .where(Source.name == source_name) \
                .one_or_none()
        
        if source is None:
            raise HTTPException(status_code=404, detail=f'Source "{source_name}" not found')
        
        subscription = await session.select(Subscription) \
                .where(
                    Subscription.source_id == source.id,
                    Subscription.name == subscription_name,
                ) \
                .options(
                    selectinload(Subscription.source),
                    selectinload(Subscription.plugin),
                ) \
                .one_or_none()
        
        if subscription is None:
            raise HTTPException(status_code=404, detail=f'Subscription "{subscription_name}" not found')
        
        return s.models.build(subscription)
    
    
    @api.get('/plugins')
    async def list_plugins() -> list[s.Plugin]:
        plugins = await session.select(Plugin) \
                .options(
                    selectinload(Plugin.source),
                ) \
                .all()
        
        return s.models.build(plugins)
    
    @api.get('/plugin/{plugin_name}')
    async def get_plugin(plugin_name: str) -> s.Plugin:
        plugin = await session.select(Plugin) \
                .where(Plugin.name == plugin_name) \
                .options(
                    selectinload(Plugin.source),
                ) \
                .one_or_none()
        
        if plugin is None:
            raise HTTPException(status_code=404, detail=f'Plugin "{plugin_name}" not found')
        
        return s.models.build(plugin)
    
    
    @api.get('/plugin/{plugin_name}/config')
    async def get_plugin_config(plugin_name: str) -> s.Form:
        success, form = await hrd.setup_plugin(plugin_name, parameters=None)
        if form is None:
            plugin = await session.plugin(plugin_name)
            form = plugin.config_form()
            form.fill(plugin.config)
        
        return s.models.build(form)
    
    @api.post('/plugin/{plugin_name}/config')
    async def update_plugin_config(plugin_name: str, params: Any = Body(...)) -> s.Form:
        success, form = await hrd.setup_plugin(plugin_name, parameters=params)
        if form is None:
            plugin = await session.plugin(plugin_name)
            form = plugin.config_form()
            form.fill(plugin.config)
        
        # TODO success?
        # error response?
        return s.models.build(form)
    
    
    @api.get('/post/{post_id}')
    async def get_post_by_id(post_id: int) -> s.Post:
        post = await session.select(RemotePost) \
                .where(
                    RemotePost.id == post_id,
                ) \
                .options(
                    selectinload(RemotePost.source),
                    selectinload(RemotePost.files),
                    selectinload(RemotePost.tags),
                ) \
                .one_or_none()
        
        if post is None:
            raise HTTPException(status_code=404, detail=f'Post id {post_id} not found')
        
        #return s.build(s.Post, post)
        return s.models.build(post)
    
    @api.get('/source/{source_name}/post/{original_id}')
    async def get_post(source_name: str, original_id: str) -> s.Post:
        source = await session.select(Source) \
                .where(Source.name == source_name) \
                .one_or_none()
        
        if source is None:
            raise HTTPException(status_code=404, detail=f'Source "{source_name}" not found')
        
        post = await session.select(RemotePost) \
                .where(
                    RemotePost.source_id == source.id,
                    RemotePost.original_id == original_id,
                ) \
                .options(
                    selectinload(RemotePost.source),
                    selectinload(RemotePost.files),
                    selectinload(RemotePost.tags),
                ) \
                .one_or_none()
        
        if post is None:
            raise HTTPException(status_code=404, detail=f'Post "{original_id}" not found')
        
        #return s.build(s.Post, post)
        return s.models.build(post)
    
    @api.get('/post/{post_id}/related')
    async def get_post_related(post_id: int) -> list[s.Post]:
        post = await session.select(RemotePost) \
                .where(
                    RemotePost.id == post_id,
                ) \
                .one_or_none()
        
        if post is None:
            raise HTTPException(status_code=404, detail=f'Post "{original_id}" not found')
        
        related_posts = await session.select(RemotePost) \
                .join(Related, RemotePost.id == Related.remote_id) \
                .where(
                    Related.related_to_id == post.id,
                ) \
                .options(
                    selectinload(RemotePost.source),
                    selectinload(RemotePost.files),
                    selectinload(RemotePost.tags),
                ) \
                .all()
        
        return s.models.build(related_posts)
    
    @api.get('/gallery/{name}')
    async def all_posts(
            name: str,
            count: int = 20,
            until: Optional[int] = None
        ) -> list[s.FeedEntry]:
        
        q_posts = session.select(Gallery) \
                        .join(RemotePost) \
                        .where(Gallery.name == name)
        
        if until is not None:
            q_posts = q_posts \
                    .where(
                        Gallery.id < cast(until, Numeric)
                    )
        
        q_posts = q_posts \
                .order_by(Gallery.id.desc()) \
                .limit(count) \
                .options(
                    selectinload(Gallery.post).selectinload(RemotePost.files),
                    selectinload(Gallery.post).selectinload(RemotePost.source),
                    selectinload(Gallery.post) \
                        .selectinload(RemotePost.related) \
                        .selectinload(Related.remote) \
                        .selectinload(RemotePost.files),
                )
        
        posts = await q_posts.all()
        
        return s.models.build([FeedEntry(sort_index=x.id, post=x.post) for x in posts])
    
    @api.get('/random')
    async def all_posts(
            count: int = 20,
            until: Optional[int] = None
        ) -> list[s.FeedEntry]:
        
        q_posts = session.select(RemotePost) \
                .order_by(func.random()) \
                .limit(count) \
                .options(
                    selectinload(RemotePost.files),
                    selectinload(RemotePost.source),
                    selectinload(RemotePost.related) \
                        .selectinload(Related.remote) \
                        .selectinload(RemotePost.files),
                )
        
        posts = await q_posts.all()
        
        return s.models.build([FeedEntry(sort_index=x.id, post=x) for x in posts])
    
    @api.get('/source/{source_name}/posts')
    async def get_source_posts(
            source_name: str,
            count: int = 20,
            until: Optional[int] = None
        ) -> list[s.FeedEntry]:
        
        source = await session.select(Source) \
                .where(Source.name == source_name) \
                .options(
                    selectinload(Source.preferred_plugin),
                ) \
                .one_or_none()
        
        if source is None:
            raise HTTPException(status_code=404, detail=f'Source "{source_name}" not found')
        
        q_posts = session.select(RemotePost) \
                .where(
                    RemotePost.source_id == source.id
                )
        
        if until is not None:
            q_posts = q_posts \
                    .where(
                        RemotePost.id < cast(until, Numeric)
                    )
        
        q_posts = q_posts \
                .order_by(RemotePost.id.desc()) \
                .limit(count) \
                .options(
                    selectinload(RemotePost.files),
                    selectinload(RemotePost.tags),
                    selectinload(RemotePost.related) \
                        .selectinload(Related.remote) \
                        .selectinload(RemotePost.files),
                )
        
        posts = await q_posts.all()
        
        return s.models.build([FeedEntry(sort_index=x.id, post=x) for x in posts])
    
    @api.get('/source/{source_name}/subscription/{subscription_name}/feed')
    async def subscription_feed(
            source_name: str,
            subscription_name: str,
            count: int = 20,
            until: Optional[int] = None
        ) -> list[s.FeedEntry]:
        
        source = await session.select(Source) \
                .where(Source.name == source_name) \
                .one_or_none()
        
        if source is None:
            raise HTTPException(status_code=404, detail=f'Source "{source_name}" not found')
        
        subscription = await session.select(Subscription) \
                .where(
                    Subscription.source_id == source.id,
                    Subscription.name == subscription_name,
                ) \
                .one_or_none()
        
        if subscription is None:
            raise HTTPException(status_code=404, detail=f'Subscription "{subscription_name}" not found')
        
        q_posts = session.select(FeedEntry) \
                .join(RemotePost) \
                .where(
                    FeedEntry.subscription_id == subscription.id
                )
        
        if until is not None:
            q_posts = q_posts \
                    .where(
                        FeedEntry.sort_index < cast(until, Numeric)
                    )
        
        q_posts = q_posts \
                .order_by(FeedEntry.sort_index.desc()) \
                .limit(count) \
                .options(
                    selectinload(FeedEntry.post).selectinload(RemotePost.files),
                    selectinload(FeedEntry.post).selectinload(RemotePost.tags),
                    selectinload(FeedEntry.post) \
                        .selectinload(RemotePost.related) \
                        .selectinload(Related.remote) \
                        .selectinload(RemotePost.files),
                )
        
        posts = await q_posts.all()
        
        return s.models.build(posts)
    
    @api.websocket('/source/{source_name}/subscription/{subscription_name}/feed')
    async def subscription_feed(websocket: WebSocket,
            source_name: str,
            subscription_name: str,
            count: int = 20,
            until: Optional[int] = None):
        
        await websocket.accept()
        
        source = await session.select(Source) \
                .where(Source.name == source_name) \
                .one_or_none()
        
        if source is None:
            raise WebSocketException(code=4404, reason=f'Source "{source_name}" not found')
        
        subscription = await session.select(Subscription) \
                .where(
                    Subscription.source_id == source.id,
                    Subscription.name == subscription_name,
                ) \
                .one_or_none()
        
        if subscription is None:
            raise WebSocketException(code=4404, reason=f'Subscription "{subscription_name}" not found')
        
        
        q_posts = session.select(FeedEntry) \
                .join(RemotePost) \
                .where(
                    FeedEntry.subscription_id == subscription.id
                ) \
        
        if until is not None:
            q_posts = q_posts \
                    .where(
                        FeedEntry.sort_index < cast(until, Numeric)
                    ) \
        
        q_posts = q_posts \
                .order_by(FeedEntry.sort_index.desc()) \
                .limit(count) \
                .options(
                    selectinload(FeedEntry.post).selectinload(RemotePost.files),
                    selectinload(FeedEntry.post).selectinload(RemotePost.tags),
                    selectinload(FeedEntry.post) \
                        .selectinload(RemotePost.related) \
                        .selectinload(Related.remote) \
                        .selectinload(RemotePost.files),
                )
        
        posts = await q_posts.stream()
        
        c = 0
        async for post in posts:
            c += 1
            await websocket.send_text(s.models.build(post).json())
            
            if c >= count:
                try:
                    data = await websocket.receive_text()
                except WebSocketDisconnect:
                    break
                
                header = s.MessageHeader(**json.loads(data))
                match header.c:
                    case 'continue':
                        c = 0
                        
                    case 'stop':
                        break
    
    
    @api.get('/search')
    async def search_remote(
            query: str,
            count: int = 20,
            until: Optional[int] = None
        ) -> list[s.FeedEntry]:
        
        q_posts = session.select(RemotePost) \
                .join(remote_post_tag) \
                .join(RemoteTag) \
                .where(
                    RemoteTag.tag == query
                )
        
        if until is not None:
            q_posts = q_posts \
                    .where(
                        RemotePost.id < cast(until, Numeric)
                    ) \
        
        q_posts = q_posts \
                .order_by(RemotePost.id.desc()) \
                .limit(count) \
                .options(
                    selectinload(RemotePost.files),
                    selectinload(RemotePost.tags),
                    selectinload(RemotePost.source),
                    selectinload(RemotePost.related) \
                        .selectinload(Related.remote) \
                        .selectinload(RemotePost.files),
                )
        
        posts = await q_posts.all()
        
        return s.models.build([FeedEntry(sort_index=x.id, post=x) for x in posts])
    
    return api


hrd = hoordu.hoordu(hoordu.load_config())
api = create_api(hrd)

app = FastAPI()
app.mount('/data', StaticFiles(directory='data'), name='data')

app.include_router(
    api,
    prefix='/api',
    tags=['api'],
)


if __name__ == '__main__':
    import uvicorn
    import sys
    
    if len(sys.argv) >= 2 and sys.argv[1] == '-d':
        uvicorn_config = uvicorn.Config(app=app, host='0.0.0.0', port=8083)
        
    else:
        uvicorn_config = uvicorn.Config(app=app, uds='/tmp/hoordu-api.sock')
    
    server = uvicorn.Server(uvicorn_config)
    
    asyncio.run(server.serve())
    
