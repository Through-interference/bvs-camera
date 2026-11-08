"""Small localhost HTTP base for the BVS controller API."""
from http.server import BaseHTTPRequestHandler
import socket
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def setup(self):
        super().setup();self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
    def reply(self,code,content,content_type):
        if isinstance(content,str):content=content.encode('utf-8')
        self.send_response(code);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(content)
    def do_GET(self):return self.reply(404,'Not found','text/plain')
