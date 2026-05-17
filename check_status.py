import zmq, msgpack
ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.setsockopt(zmq.LINGER, 0)
sock.connect('tcp://127.0.0.1:5558')
sock.send(msgpack.packb('MODULES'))
import time; time.sleep(0.5)
reply = sock.recv()
data = msgpack.unpackb(reply, raw=False)
for m in data.get('modules', []):
    print(f"module_id={m['module_id']} interfaces={m['interfaces']} liveness={m['liveness']} last_seen={m['last_seen']}")
sock.close()
ctx.destroy(linger=0)
