"""Bounded PTY relay, instantiated only inside the protected root runner."""
import base64
import fcntl
import os
import pty
import struct
import subprocess
import termios
import threading

class TerminalRelay:
    def __init__(self,argv,env,demote):
        master,slave=pty.openpty()
        self.master=master; self.lock=threading.Lock();self.buffer=bytearray();self.offset=0
        self.resize(100,30)
        def child():
            os.setsid();fcntl.ioctl(slave,termios.TIOCSCTTY,0);demote()
        self.process=subprocess.Popen(argv,env={**env,'TERM':'xterm-256color'},preexec_fn=child,
            stdin=slave,stdout=slave,stderr=slave,close_fds=True)
        os.close(slave)
        threading.Thread(target=self.drain,daemon=True).start()
    def resize(self,cols,rows):
        if type(cols) is not int or type(rows) is not int or not 10<=cols<=300 or not 4<=rows<=150:
            raise ValueError('Invalid terminal size')
        fcntl.ioctl(self.master,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
    def drain(self):
        try:
            while True:
                chunk=os.read(self.master,8192)
                if not chunk:break
                with self.lock:
                    self.buffer.extend(chunk)
                    if len(self.buffer)>1048576:
                        drop=len(self.buffer)-1048576;del self.buffer[:drop];self.offset+=drop
        except OSError:pass
    def request(self,body):
        action=body.get('action','read')
        if action=='write':
            raw=base64.b64decode(body.get('data',''),validate=True)
            if len(raw)>8192:raise ValueError('Terminal input too large')
            os.write(self.master,raw)
        elif action=='resize':self.resize(body.get('cols'),body.get('rows'))
        elif action!='read':raise ValueError('Unavailable terminal action')
        cursor=body.get('cursor',0)
        if type(cursor) is not int or cursor<0:raise ValueError('Invalid terminal cursor')
        with self.lock:
            start=max(self.offset,min(cursor,self.offset+len(self.buffer)))
            raw=bytes(self.buffer[start-self.offset:start-self.offset+32768])
            return {'data':base64.b64encode(raw).decode(),'cursor':start+len(raw),'truncated':cursor<self.offset,
                    'exit_code':self.process.poll()}
