#!/usr/bin/env python

from database import *
from api import MisskeyApi

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import dateutil.parser
from datetime import datetime
import time
import json
import traceback

class StopScraping(BaseException):
    pass


STOP_AFTER = 24 * 60 * 60

api = MisskeyApi('sqKESNxorp0YW76e')


def process_note(session, tnote):
    note = session.scalars(select(Note).where(Note.id == tnote.id)).one_or_none()
    if note is not None:
        return note
    
    note = Note(
        id=tnote.id,
        cw=tnote.cw,
        text=tnote.text,
        renote_count=tnote.renoteCount,
        react_count=sum(tnote.reactions.values()),
        reaction=tnote.get('myReaction', None),
        note_time=dateutil.parser.isoparse(tnote.createdAt),
    )
    
    if tnote.contains('renote'):
        note.renote = process_note(session, tnote.renote)
    
    user = session.scalars(select(User).where(User.id == tnote.user.id)).one_or_none()
    if user is None:
        user = User(
            id=tnote.user.id,
            username=tnote.user.username,
            name=tnote.user.name,
            avatar_url=tnote.user.avatarUrl,
            # most likely not following
            is_following=0,
        )
        
    else:
        user.name = tnote.user.name
    
    note.user = user
    session.add(user)
    
    # file should be unique every time, we already checked for the note
    for tfile in tnote.files:
        file = session.scalars(select(File).where(File.id == tfile.id)).one_or_none()
        if file is None:
            file = File(
                id=tfile.id,
                name=tfile.name,
                type=tfile.type,
                url=tfile.url,
                thumbnail_url=tfile.thumbnailUrl,
            )
        
        note.files.append(file)
    
    session.add(note)
    return note


engine = create_engine('sqlite:///misskey.db')
with Session(engine, expire_on_commit=False) as session, session.begin():
    latest_post = session.scalars(select(Note).order_by(Note.id.desc()).limit(1)).one_or_none()
    
    try:
        with open('state.json', 'r') as f:
            state = json.load(f)
        
        state.insert(0, [None, None])
        
    except:
        if latest_post is not None:
            state = [
                [None, None],
                [latest_post.id, None],
            ]
            
        else:
            state = [
                [None, None],
            ]
    
    try:
        i = 0
        while i < len(state) - 1:
            print(i)
            if state[i][1] == state[i + 1][0]:
                state[i][1] = state[i + 1][1]
                del state[i + 1]
                continue
            
            head = state[i + 1][0]
            try:
                first_note = True
                while True:
                    for tnote in api.timeline(until_id=state[i][1]):
                        print(f'saving {tnote.id}')
                        try:
                            note = process_note(session, tnote)
                            
                            if first_note:
                                state[i][0] = note.id
                                first_note = False
                            
                            if head is not None and head >= note.id:
                                state[i][1] = state[i + 1][1]
                                del state[i + 1]
                                raise StopScraping
                                
                            if STOP_AFTER is not None:
                                date = note.note_time
                                now = datetime.now(tz=date.tzinfo)
                                if abs((now - date).total_seconds()) > STOP_AFTER:
                                    state[i][1] = None
                                    del state[i + 1]
                                    raise StopScraping
                            
                        except Exception:
                            print(tnote)
                            raise
                        
                        state[i][1] = tnote.id
                    
                    print('sleeping for 5 seconds')
                    time.sleep(5)
                
            except StopScraping:
                pass
            
            i += 1
            
    except Exception:
        print(state)
        traceback.print_exc()
        pass
        
    except:
        pass
    
    # prevent getting any older posts than what we already have
    state[-1][1] = None
    
    with open('state.json', 'w+') as f:
        json.dump(state, f)
