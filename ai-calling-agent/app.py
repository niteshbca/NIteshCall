import os, re, json, uuid, threading, time, fcntl
from pathlib import Path
from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
ROOT=Path(os.getenv('APP_ROOT', str(Path(__file__).parent)))
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
app=Flask(__name__)
@app.before_request
def auth():
    if request.path == '/dashboard': return None
    token=os.getenv('ADMIN_TOKEN','')
    if not token or request.headers.get('Authorization') != 'Bearer '+token:
        return Response('Supply Authorization: Bearer ADMIN_TOKEN',401)
def save(path, value):
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,ensure_ascii=False)); tmp.replace(path)
def worker(cid, lock):
    path=DATA/(cid+'.json'); state=json.loads(path.read_text())
    try:
        endpoint=os.getenv('SIP_ENDPOINT','gsm-gateway')
        caller=os.getenv('CALLER_ID','AI Assistant')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',endpoint) or any(c in caller for c in '\r\n'):
            raise ValueError('Invalid SIP endpoint/caller ID')
        for row in state['calls']:
            if (DATA/(cid+'.stop')).exists(): break
            row['status']='dialing'; save(path,state)
            name=uuid.uuid4().hex+'.call'
            staging=Path('/var/spool/asterisk/ai-staging')/name
            outgoing=Path('/var/spool/asterisk/outgoing')/name
            archive=Path('/var/spool/asterisk/outgoing_done')/name
            staging.write_text(f'Channel: PJSIP/{row["number"]}@{endpoint}\nCallerid: {caller}\nMaxRetries: 0\nWaitTime: 45\nContext: ai-outbound\nExtension: s\nPriority: 1\nSetvar: CAMPAIGN_ID={cid}\nArchive: yes\n')
            staging.replace(outgoing)
            # Never advance until Asterisk archives this completed call.
            deadline=time.monotonic()+720
            while not archive.exists():
                if time.monotonic()>deadline:
                    raise TimeoutError('Call completion unknown; queue stopped to avoid overlapping calls. Check Asterisk.')
                time.sleep(1)
            text=archive.read_text()
            row['status']='completed' if 'Status: Completed' in text else 'failed'
            save(path,state)
        state['status']='stopped' if (DATA/(cid+'.stop')).exists() else 'finished'
    except Exception as e:
        state['status']='error'; state['error']=str(e)
    finally:
        save(path,state); fcntl.flock(lock,fcntl.LOCK_UN); lock.close()
@app.get('/dashboard')
def dashboard():
    return Response((ROOT/'dashboard.html').read_text(), mimetype='text/html')
@app.get('/')
def home():
    return jsonify(service='AI Calling Agent',create='POST /campaigns',status='GET /campaigns/<id>',stop='POST /campaigns/<id>/stop',form='Open dashboard.html locally')
@app.post('/campaigns')
def create():
    body=request.get_json(silent=True) or {}
    message=body.get('message',''); numbers=body.get('numbers',[])
    if not isinstance(message,str) or not 1<=len(message.strip())<=20000 or not isinstance(numbers,list) or not 1<=len(numbers)<=1000:
        return jsonify(error='Message and 1–1000 numbers required'),400
    if any(not isinstance(n,str) or not re.fullmatch(r'\+?[0-9]{8,15}',n) for n in numbers):
        return jsonify(error='Invalid phone number; use digits and optional leading +'),400
    lock=open(DATA/'queue.lock','a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close(); return jsonify(error='Another campaign is running'),409
    cid=uuid.uuid4().hex
    save(DATA/(cid+'.json'),dict(id=cid,message=message,status='running',calls=[dict(number=n,status='pending') for n in dict.fromkeys(numbers)]))
    threading.Thread(target=worker,args=(cid,lock),daemon=True).start()
    return jsonify(id=cid),201
@app.get('/campaigns/<cid>')
def status(cid):
    if not re.fullmatch(r'[a-f0-9]{32}',cid): return '',404
    path=DATA/(cid+'.json')
    return jsonify(json.loads(path.read_text())) if path.exists() else ('',404)
@app.post('/campaigns/<cid>/stop')
def stop(cid):
    if not re.fullmatch(r'[a-f0-9]{32}',cid) or not (DATA/(cid+'.json')).exists(): return '',404
    (DATA/(cid+'.stop')).touch()
    return jsonify(message='Stops after current call ends')
if __name__=='__main__': app.run(host='127.0.0.1',port=8080)
