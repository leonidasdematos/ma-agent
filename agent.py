#!/usr/bin/env python3
import os, sys, json, time, shutil, zipfile, subprocess, threading
import socket
from datetime import datetime
import traceback

# --- Bluetooth (RFCOMM SPP)  ---
try:
    from bluetooth import BluetoothSocket, advertise_service, RFCOMM
    BT_AVAILABLE = True
except Exception:
    BT_AVAILABLE = False

LOG = "/var/log/ma-agent/agent.log"
AGENT_DIR = "/opt/ma-agent"
UPDATES_DIR = "/opt/ma-agent/updates"
VERSION_FILE = "/opt/ma-agent/VERSION.txt"

os.makedirs(UPDATES_DIR, exist_ok=True)

def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def read_version():
    try:
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    except:
        return "0.0.1-dev"

STATE = {
    "version": read_version(),
    "uptime_start": time.time(),
    "job_running": False,
    "last_cmd": None,
}

def handle_cmd(cmd):
    """
    Protocolo: uma linha JSON por mensagem.
    Exemplo:
      {"type":"PING"}
      {"type":"INFO"}
      {"type":"START_JOB","payload":{"field":"Talhao 1"}}
      {"type":"UPDATE","payload":{"name":"update_1.2.3.zip","content_b64":"..."}}
    """
    STATE["last_cmd"] = cmd
    ctype = cmd.get("type", "").upper()
    payload = cmd.get("payload", {})

    if ctype == "PING":
        return {"ok": True, "type": "PONG", "ts": time.time()}

    if ctype == "INFO":
        up = int(time.time() - STATE["uptime_start"])
        return {"ok": True, "type": "INFO",
                "version": STATE["version"],
                "uptime_s": up}

    if ctype == "GET_STATUS":
        return {"ok": True, "type": "STATUS",
                "job_running": STATE["job_running"]}

    if ctype == "START_JOB":
        STATE["job_running"] = True
        return {"ok": True, "type": "ACK", "detail": "job started"}

    if ctype == "STOP_JOB":
        STATE["job_running"] = False
        return {"ok": True, "type": "ACK", "detail": "job stopped"}

    if ctype == "UPDATE":
        # payload: {"name": "update_x.y.z.zip", "content_b64": "<...>"}
        import base64
        name = payload.get("name")
        data_b64 = payload.get("content_b64")
        if not name or not data_b64:
            return {"ok": False, "error": "missing name or content_b64"}

        target = os.path.join(UPDATES_DIR, name)
        with open(target, "wb") as f:
            f.write(base64.b64decode(data_b64))

        # Descompactar e aplicar (ex.: sobrescrever /opt/ma-agent/code/*)
        try:
            with zipfile.ZipFile(target, 'r') as z:
                z.extractall(AGENT_DIR)
            # atualizar versão, se veio VERSION.txt
            STATE["version"] = read_version()
            # reiniciar serviço para aplicar (opcional: postergar)
            subprocess.run(["sudo", "systemctl", "restart", "ma-agent"], check=False)
            return {"ok": True, "type": "ACK", "detail": "update applied, restarting"}
        except Exception as e:
            return {"ok": False, "error": f"update failed: {str(e)}"}

    if ctype == "REBOOT":
        subprocess.Popen(["sudo", "reboot"])
        return {"ok": True, "type": "ACK", "detail": "rebooting"}

    return {"ok": False, "error": f"unknown type: {ctype}"}

def serve_stream(conn, addr_desc):
    """
    Lê JSON por linha (\n) e responde JSON por linha usando recv/sendall,
    compatível com TCP e RFCOMM (PyBluez).
    """
    log(f"client connected: {addr_desc}")
    buffer = b""
    try:
        while True:
            chunk = conn.recv(1024)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                text = line.decode("utf-8", errors="ignore").strip()
                if not text:
                    continue
                log(f"recv {addr_desc}: {text}")
                try:
                    cmd = json.loads(text)
                    resp = handle_cmd(cmd)
                except Exception as e:
                    resp = {"ok": False, "error": f"bad_json: {str(e)}"}
                out = (json.dumps(resp) + "\n").encode("utf-8")
                conn.sendall(out)
    except Exception as e:
        log(f"stream error: {e}\n{traceback.format_exc()}")
    finally:
        try: conn.close()
        except: pass
        log(f"client disconnected: {addr_desc}")


def tcp_server():
    # Útil para testes via Wi-Fi: echo -n '{"type":"PING"}\n' | nc ma-gateway 7777
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("0.0.0.0", 7777))
    s.listen(1)
    log("TCP server listening on 0.0.0.0:7777")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=serve_stream, args=(conn, f"tcp:{addr}"), daemon=True).start()

def bt_server():
    if not BT_AVAILABLE:
        log("Bluetooth lib not available (PyBluez); skipping BT server")
        return
    try:
        sock = BluetoothSocket(RFCOMM)
        sock.bind(("", 1))  # canal 1
        sock.listen(1)
        try:
            advertise_service(sock,
                              "MAGateway",
                              service_id="00001101-0000-1000-8000-00805F9B34FB",
                              service_classes=["00001101-0000-1000-8000-00805F9B34FB"],
                              profiles=[("00001101-0000-1000-8000-00805F9B34FB", 1)])
            log("Bluetooth SPP advertised via SDP")
        except Exception as e:
            # se falhar o advertise, seguimos assim mesmo — já registramos SPP com `sdptool add SP`
            log(f"Bluetooth advertise skipped: {e}; relying on pre-added SPP (sdptool add SP)")
        log("Bluetooth SPP listening on RFCOMM ch 1")
        while True:
            client, addr = sock.accept()
            threading.Thread(target=serve_stream, args=(client, f"bt:{addr}"), daemon=True).start()
    except Exception as e:
        log(f"Bluetooth server init error: {e}\n{traceback.format_exc()}")


def main():
    log(f"ma-agent starting v{STATE['version']}")
    # Inicia TCP e BT em threads
    threading.Thread(target=tcp_server, daemon=True).start()
    threading.Thread(target=bt_server, daemon=True).start()  # se falhar, só TCP
    # Loop de “vida”
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
