#!/usr/bin/env python

from database import *
from sqlalchemy import create_engine

engine = create_engine('sqlite:///misskey.db')
Base.metadata.create_all(engine)
