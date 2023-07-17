import requests
import json

DOMAIN = 'https://misskey.io'

class Dynamic(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        else:
            raise AttributeError
    
    def __setattr__(self, name, value):
        self[name] = value
    
    def contains(self, *keys):
        return all(self.get(key) is not None for key in keys)
    
    @classmethod
    def from_json(cls, json_string):
        if json_string is None:
            return cls()
        
        try:
            s = json.loads(json_string, object_hook=cls)
        except ValueError:
            print(json_string)
            raise
        
        return s

class MisskeyApi:
    def __init__(self, token):
        self.token = token
        self.session = requests.Session()
    
    def timeline(self, until_id=None):
        url = DOMAIN + '/api/notes/timeline'
        
        data = {
            'withReplies': False,
            'limit': 10,
            'i': self.token,
        }
        if until_id is not None:
            data['limit'] = 30
            data['untilId'] = until_id
        
        response = self.session.post(url, json=data)
        timeline = Dynamic.from_json(response.text)
        
        return timeline
    
    def renote(self, note_id):
        url = DOMAIN + '/api/notes/create'
        data = {
            'renoteId': note_id,
            'i': self.token,
        }
        response = self.session.post(url, json=data)
        return
    
    def react(self, note_id, reaction='❤'):
        url = DOMAIN + '/api/notes/reactions/create'
        data = {
            'noteId': note_id,
            'reaction': reaction,
            'i': self.token,
        }
        response = self.session.post(url, json=data)
        return
    
    def delete_react(self, note_id):
        url = DOMAIN + '/api/notes/reactions/delete'
        data = {
            'noteId': note_id,
            'i': self.token,
        }
        response = self.session.post(url, json=data)
        return
    
    def user(self, user_id):
        url = DOMAIN + '/api/users/show'
        data = {
            'userId': user_id,
            'i': self.token,
        }
        response = self.session.post(url, json=data)
        return Dynamic.from_json(response.text)
    
    def follow(self, user_id):
        url = DOMAIN + '/api/following/create'
        data = {
            'userId': user_id,
            'i': self.token,
        }
        response = self.session.post(url, json=data)
        return Dynamic.from_json(response.text)


