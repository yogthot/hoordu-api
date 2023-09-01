#!/bin/sh
/usr/bin/uvicorn server:app --uds /tmp/hoordu-api.sock --reload

