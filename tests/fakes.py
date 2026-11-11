from telethon.tl.types import User


def make_user(uid=100, first="Me", username=None, is_self=True):
    return User(
        id=uid, is_self=is_self, contact=False, mutual_contact=False, deleted=False,
        bot=False, bot_chat_history=False, bot_nochats=False, verified=False,
        restricted=False, min=False, bot_inline_geo=False, support=False, scam=False,
        fake=False, access_hash=1, first_name=first, username=username,
    )


class FakeDialog:
    def __init__(self, cid, name, username=None):
        self.id = cid
        self.name = name
        self.is_group = True
        self.is_channel = False
        self.entity = type("Entity", (), {"username": username})()


class FakeDoc:
    def __init__(self, mime_type="image/gif", size=0):
        self.mime_type = mime_type
        self.size = size
        self.attributes = []


class FakeMsg:
    def __init__(self, path=None, mime_type="image/gif"):
        self.gif = None
        self.document = FakeDoc(mime_type=mime_type, size=0)
        self.path = path

    async def download_media(self, file):
        import shutil

        if not self.path:
            return None
        shutil.copy(self.path, file)
        return file


class FakeEvent:
    def __init__(
        self,
        text,
        private=True,
        sender=None,
        chat_id=-1001000000001,
        chat_title="Chat",
        reply=None,
        message=None,
    ):
        self.text = text
        self.is_private = private
        self.is_group = not private
        self.is_channel = False
        self.is_reply = reply is not None
        self.chat_id = chat_id
        self.id = 1
        self.out = False
        self._sender = sender or make_user()
        self.sender_id = self._sender.id
        self.chat = type("Chat", (), {"title": chat_title})()
        self._reply = reply
        self.message = message
        self.replies = []

    async def get_sender(self):
        return self._sender

    async def reply(self, text, parse_mode=None):
        self.replies.append(text)
        return text

    async def get_reply_message(self):
        return self._reply
