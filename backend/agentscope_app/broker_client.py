import json, socket
from .config import BROKER_SOCKET

def call(message: dict, timeout=30):
    s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(timeout)
    try:
        s.connect(str(BROKER_SOCKET))
        s.sendall(json.dumps(message,ensure_ascii=False).encode()+b"\n")
        data=b""
        while not data.endswith(b"\n"):
            chunk=s.recv(65536)
            if not chunk: break
            data+=chunk
        result=json.loads(data.decode()) if data else {"ok":False,"error":"broker closed the connection"}
        if not result.get("ok",False): raise RuntimeError(result.get("error","broker operation failed"))
        return result.get("result",{})
    finally: s.close()
