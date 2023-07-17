#!/usr/bin/env python

import uvloop
uvloop.install()
import asyncio


from database import *
from api import MisskeyApi
import schemas

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from fastapi import FastAPI, WebSocket, Depends
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, Response
from starlette.websockets import WebSocketDisconnect

import json
from datetime import datetime, timedelta

engine = create_engine('sqlite:///misskey.db', connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI()
app.mount('/static', StaticFiles(directory='static'), name='static')

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_api():
    yield MisskeyApi('sqKESNxorp0YW76e')

@app.get('/')
async def root():
    return FileResponse('index.html')


@app.get('/react')
async def react(note_id: str, reaction: str, api: MisskeyApi = Depends(get_api), session: Session = Depends(get_db)):
    note = session.scalars(select(Note).where(Note.id == note_id)).one_or_none()
    if note is None:
        return Response(status_code=404)
    
    if note.reaction is not None:
        api.delete_react(note_id)
        pass
    
    note.reaction = reaction
    session.add(note)
    api.react(note_id, reaction)
    session.commit()
    return Response(status_code=204)

@app.get('/renote')
async def renote(note_id: str, api: MisskeyApi = Depends(get_api), session: Session = Depends(get_db)):
    api.renote(note_id)
    return Response(status_code=204)


@app.websocket('/timeline')
async def timeline(websocket: WebSocket, count: int = 20, session: Session = Depends(get_db)):
    await websocket.accept()
    
    now = datetime.utcnow()
    yesterday = datetime.utcnow() - timedelta(hours=24)
    db_notes = session.scalars(select(Note).where(Note.note_time > yesterday)).all()
    
    notes = []
    for note in db_notes:
        if len(note.files) == 0:
            continue
        
        if note.renote_id is not None:
            continue
        
        timediff = (now - note.note_time).total_seconds()
        #rating = (note.renote_count + note.react_count) / timediff
        rating = 1 / timediff
        
        notes.append((rating, note))
    
    notes = sorted(notes, key=lambda n: n[0], reverse=True)
    notes = [n[1] for n in notes]
    
    c = 0
    for note in notes:
        if c >= count:
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            
            command = json.loads(data)
            match command:
                case {'command': 'continue'}:
                    c = 0
                    
                case {'command': 'stop'}:
                    break
        
        await websocket.send_text(schemas.Note.from_orm(note).json())
        c += 1


async def serve():
    import uvicorn
    import sys
    
    if len(sys.argv) >= 2 and sys.argv[1] == '-d':
        uvicorn_config = uvicorn.Config(app=app, host='0.0.0.0', port=8082)
        
    else:
        uvicorn_config = uvicorn.Config(app=app, uds='asgi.sock')
    
    server = uvicorn.Server(uvicorn_config)
    await server.serve()

if __name__ == '__main__':
    asyncio.run(serve())
    
