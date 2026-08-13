"""DataLinkTargetService (DLT) process management and streaming transport.

This module mirrors the vendor ``common.py`` helper utilities (host check,
DLT connect/exec) plus the background thread that receives raw timestamp
chunks over a per-channel ZMQ PAIR socket. It has no dependency on the SCPI
control class in :mod:`labtools.devices.idq_time_controller.controller`, so it
can be tested or reused independently.
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import time
from pathlib import Path
from threading import Thread
from typing import Callable, Optional

import numpy as np
import zmq

logger = logging.getLogger(__name__)

DLT_PORT = 6060
DEFAULT_DLT_PATH = Path("C:/Program Files/IDQ/Time Controller/packages/ScpiClient")


def check_host(address: str, port: int) -> bool:
    """Return True if a TCP connection to ``address:port`` succeeds."""
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((address, port))
        return True
    except socket.error:
        return False
    finally:
        s.close()


def dlt_connect(output_dir: Path, dlt_path: Path = DEFAULT_DLT_PATH) -> zmq.Socket:
    """Start the DataLinkTargetService if needed and return a connected ZMQ socket."""
    if dlt_path.is_dir():
        dlt_bin = dlt_path / "DataLinkTargetService.exe"
        dlt_dir = dlt_path
    else:
        dlt_bin = dlt_path
        dlt_dir = dlt_path.parent

    if not dlt_bin.exists():
        raise FileNotFoundError(f"DataLinkTargetService binary not found: {dlt_bin}")

    if not check_host("localhost", DLT_PORT):
        config_template = dlt_dir / "config" / "DataLinkTargetService.log.conf"
        log_conf = output_dir / "DataLinkTargetService.log.conf"

        if config_template.exists():
            with config_template.open() as tmpl, log_conf.open("w") as out:
                for line in tmpl:
                    out.write(
                        line.replace(
                            "log4cplus.appender.AppenderFile.File=",
                            f"log4cplus.appender.AppenderFile.File={output_dir}/",
                        )
                    )
            subprocess.Popen(
                [str(dlt_bin), "-f", str(output_dir), "--logconf", str(log_conf)],
                stdout=subprocess.PIPE,
                cwd=str(output_dir),
            )
        else:
            subprocess.Popen(
                [str(dlt_bin), "-f", str(output_dir)],
                stdout=subprocess.PIPE,
                cwd=str(output_dir),
            )

        deadline = time.time() + 10.0
        while time.time() < deadline:
            if check_host("localhost", DLT_PORT):
                break
            time.sleep(0.2)
        if not check_host("localhost", DLT_PORT):
            raise ConnectionError(
                "DataLinkTargetService did not start listening on localhost:6060. "
                f"Checked executable at {dlt_bin}."
            )

    context = zmq.Context()
    sock = context.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, 2000)
    sock.setsockopt(zmq.SNDTIMEO, 2000)
    sock.connect(f"tcp://localhost:{DLT_PORT}")
    return sock


def dlt_exec(sock: zmq.Socket, command: str):
    """Send a command to the DLT service and return the parsed JSON response."""
    try:
        sock.send_string(command)
        raw = sock.recv().decode("utf-8")
    except zmq.Again as exc:
        raise TimeoutError(f"DataLinkTarget did not respond to command: {command!r}") from exc

    answer = json.loads(raw) if raw.strip() else None

    if isinstance(answer, dict) and "error" in answer:
        msg = answer.get("error", {}).get("description", "unknown error")
        raise RuntimeError(f"DataLinkTarget error: {msg}")

    return answer


class StreamClient(Thread):
    """Background thread that receives binary timestamp chunks from the DLT
    and delivers them as numpy arrays to a user callback."""

    def __init__(
        self,
        addr: str,
        channel: int,
        callback: Callable[[int, np.ndarray], None],
    ):
        super().__init__(daemon=True)
        self.channel = channel
        self.callback = callback
        self._addr = addr
        self._running = False

    def run(self) -> None:
        context = zmq.Context()
        sock = context.socket(zmq.PAIR)
        sock.connect(self._addr)

        monitor = sock.get_monitor_socket()
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        poller.register(monitor, zmq.POLLIN)

        self._running = True
        try:
            while self._running:
                for ready, *_ in poller.poll(timeout=500):
                    if ready is sock:
                        data = sock.recv()
                        if len(data) == 0:
                            self._running = False
                            break
                        # Each timestamp is a 64-bit little-endian integer (ps)
                        n = len(data) // 8
                        if n > 0:
                            ts = np.frombuffer(data[: n * 8], dtype="<i8")
                            self.callback(self.channel, ts)
                    elif ready is monitor:
                        from zmq.utils.monitor import recv_monitor_message
                        evt = recv_monitor_message(monitor)
                        if evt["event"] == zmq.EVENT_DISCONNECTED:
                            self._running = False
        finally:
            poller.unregister(sock)
            poller.unregister(monitor)
            monitor.close()
            sock.close()
            context.term()

    def join(self, timeout: Optional[float] = None) -> None:
        self._running = False
        super().join(timeout)
