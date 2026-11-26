#!/usr/bin/env python3
import argparse, json, secrets, signal, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"; DATA.mkdir(exist_ok=True)
TOKEN_FILE = DATA / "access-token"
TOKEN = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else secrets.token_urlsafe(24)
if not TOKEN_FILE.exists(): TOKEN_FILE.write_text(TOKEN + "\n"); TOKEN_FILE.chmod(0o600)
STATE = {"state":"IDLE","motor_backend":"mock","camera":{"status":"verified","device":"/dev/video9","fps":29.9},"npu":{"status":"verified","runtime":"1.0.0","driver":"0.4.2","model":"ssd_inception_v2_int8","fps":6.809,"p95_ms":148.297,"stability_iterations":4000},"objects":[],"events":[]}

def event(kind, detail=""):
    STATE["events"].append({"time":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"type":kind,"detail":detail})
    STATE["events"] = STATE["events"][-200:]

class Handler(SimpleHTTPRequestHandler):
    def auth(self):
        return self.headers.get("Authorization") == f"Bearer {TOKEN}" or self.headers.get("X-M10-Token") == TOKEN
    def send_json(self, status, payload):
        body=json.dumps(payload,ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/":
            page=(ROOT/"web/index.html").read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(page))); self.end_headers(); self.wfile.write(page); return
        if not self.auth(): return self.send_json(401,{"error":"pairing_token_required"})
        if self.path == "/api/status": return self.send_json(200,STATE)
        if self.path == "/api/objects": return self.send_json(200,STATE["objects"])
        if self.path == "/api/events": return self.send_json(200,STATE["events"])
        if self.path == "/api/config": return self.send_json(200,{"source":"configs/default.yaml","writes_disabled":True})
        if self.path == "/api/stream": return self.send_json(503,{"error":"stream_not_started","camera_verified":True})
        self.send_json(404,{"error":"not_found"})
    def do_POST(self):
        if not self.auth(): return self.send_json(401,{"error":"pairing_token_required"})
        actions={"/api/action/search_pet":"SEARCH_PET","/api/action/search_owner":"SEARCH_OWNER","/api/action/follow_pet":"FOLLOW_PET","/api/action/follow_owner":"FOLLOW_OWNER","/api/action/stop":"IDLE","/api/action/emergency_stop":"EMERGENCY_STOP"}
        if self.path in actions:
            STATE["state"]=actions[self.path]; event("EMERGENCY_STOP" if "emergency" in self.path else "ACTION",STATE["state"]); return self.send_json(200,{"ok":True,"state":STATE["state"],"motor":"mock"})
        if self.path == "/api/enroll/owner/start": event("OWNER_ENROLL_REQUESTED","waiting_for_face_models"); return self.send_json(409,{"error":"face_models_not_deployed","data_remains_local":True})
        if self.path == "/api/enroll/owner/cancel": event("OWNER_ENROLL_CANCELLED"); return self.send_json(200,{"ok":True})
        self.send_json(404,{"error":"not_found"})
    def do_DELETE(self):
        if not self.auth(): return self.send_json(401,{"error":"pairing_token_required"})
        if self.path == "/api/enroll/owner":
            owner=DATA/"owners"; removed=0
            if owner.exists():
                for item in owner.glob("*"): item.unlink(); removed+=1
            event("OWNER_DATA_DELETED",str(removed)); return self.send_json(200,{"ok":True,"removed":removed})
        self.send_json(404,{"error":"not_found"})
    def log_message(self, fmt, *args): print(time.strftime("%F %T"),fmt%args,flush=True)

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--host",default="127.0.0.1"); parser.add_argument("--port",type=int,default=8080); args=parser.parse_args()
    event("SERVER_STARTED"); print("SERVER_READY",flush=True); server=ThreadingHTTPServer((args.host,args.port),Handler)
    signal.signal(signal.SIGTERM,lambda *_: threading.Thread(target=server.shutdown,daemon=True).start()); server.serve_forever(); server.server_close()
