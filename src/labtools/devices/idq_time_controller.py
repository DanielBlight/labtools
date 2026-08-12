"""IDQuantique Time Controller wrapper.

Wraps the ZMQ SCPI interface into a class with methods for the three
acquisition modes used in this lab:

* **Counts** — read input event counts over an integration window
* **Histograms** — time-resolved photon arrival histograms (TCSPC)
* **Timestamps (streaming)** — on-the-fly delivery of raw timestamps via a
  callback, suitable for autocorrelation without accumulating large files

The class does not depend on the vendor example utilities directly; all SCPI
commands are issued through the private :meth:`_cmd` / :meth:`_query` helpers
so the communication layer is easy to swap later if needed.

Requirements
------------
* ``pyzmq`` must be installed in the environment.
* For timestamp streaming the DataLinkTargetService (DLT) executable must be
  reachable; its default path is ``DEFAULT_DLT_PATH`` below.

Usage example
-------------
::

    tc = IDQTimeController("169.254.99.100")
    with tc:
        tc.configure_channel(1, threshold_v=0.1, edge="rising", delay_ps=0)
        tc.configure_histogram(hist=1, stop_channel=1, ref_channel="start",
                               bin_width_ps=13, bin_count=1024)

        counts = tc.get_counts(channel=1, duration_s=1.0)

        x_ps, y = tc.get_histogram(hist=1, duration_s=1.0)

        def on_chunk(channel, timestamps_ps):
            ...  # process chunk on the fly

        tc.start_timestamp_stream(channels=[1], callback=on_chunk)
        time.sleep(5)
        tc.stop_timestamp_stream()
"""

import time
import struct
import logging
import socket
import subprocess
from pathlib import Path
from threading import Thread
from typing import Callable, Dict, Iterable, List, Optional

import zmq
import numpy as np

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

SCPI_PORT = 5555
DLT_PORT = 6060
DEFAULT_DLT_PATH = Path("C:/Program Files/IDQ/Time Controller/packages/ScpiClient")

# The vendor RAW channel block name for channel n is RAW<n>.
# Streaming uses per-channel ZMQ PAIR sockets on ports starting here.
_STREAM_BASE_PORT = 4241


# ------------------------------------------------------------------
# Main class
# ------------------------------------------------------------------

class IDQTimeController:
    """Control an IDQuantique Time Controller over its SCPI/ZMQ interface.

    Parameters
    ----------
    address : str
        IP address of the Time Controller (e.g. ``"169.254.99.100"``).
    dlt_path : Path
        Path to the DataLinkTargetService executable directory or binary.
        Only required when using timestamp streaming.
    """

    def __init__(
        self,
        address: str,
        dlt_path: Path = DEFAULT_DLT_PATH,
    ):
        self.address = address
        self.dlt_path = dlt_path

        self._context: Optional[zmq.Context] = None
        self._tc: Optional[zmq.Socket] = None          # SCPI socket
        self._dlt: Optional[zmq.Socket] = None         # DataLink socket
        self._stream_clients: Dict[int, "_StreamClient"] = {}

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def connect(self):
        """Open the SCPI connection to the Time Controller."""
        if not _check_host(self.address, SCPI_PORT):
            raise ConnectionError(
                f"Cannot reach Time Controller at {self.address}:{SCPI_PORT}. "
                "Check network and that the device is powered on."
            )
        self._context = zmq.Context()
        self._tc = self._context.socket(zmq.REQ)
        self._tc.connect(f"tcp://{self.address}:{SCPI_PORT}")
        logger.info(f"Connected to Time Controller at {self.address}")

    def disconnect(self):
        """Close all open connections and stop any active streams."""
        self.stop_timestamp_stream()
        if self._dlt is not None:
            try:
                self._dlt.close()
            except Exception:
                pass
            self._dlt = None
        if self._tc is not None:
            try:
                self._tc.close()
            except Exception:
                pass
            self._tc = None
        if self._context is not None:
            try:
                self._context.term()
            except Exception:
                pass
            self._context = None
        logger.info("Disconnected from Time Controller")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    # ------------------------------------------------------------------
    # Channel configuration
    # ------------------------------------------------------------------

    def configure_channel(
        self,
        channel: int,
        *,
        threshold_v: float = 0.1,
        edge: str = "rising",
        delay_ps: int = 0,
        enabled: bool = True,
    ):
        """Configure an input channel.

        Parameters
        ----------
        channel : int
            Channel number (1–4) or ``0`` for the START input.
        threshold_v : float
            Trigger threshold in **volts** (e.g. ``0.1`` for a TTL-level
            signal). Sent to the device as ``INPUt<n>:THREshold <value>V``.
        edge : str
            ``"rising"`` or ``"falling"``.
        delay_ps : int
            Additional delay in picoseconds applied via the channel's DELA
            block.
        enabled : bool
            Whether to enable the channel.
        """
        block = "STAR" if channel == 0 else f"INPU{channel}"
        edge_scpi = "RISING" if edge.lower() == "rising" else "FALLing"
        ena_scpi = "ON" if enabled else "OFF"

        self._cmd(f"{block}:COUP DC")
        self._cmd(f"{block}:EDGE {edge_scpi}")
        self._cmd(f"{block}:THRE {threshold_v:+.3f}V")
        self._cmd(f"{block}:SELE UNSHAPED")
        self._cmd(f"{block}:ENAB {ena_scpi}")
        self._cmd(f"{block}:HIRES:ERROR:CLEAR")

        if channel != 0:
            self._cmd(f"DELA{channel}:VALU {int(delay_ps)}")
            self._cmd(f"DELA{channel}:LINK INPU{channel}")

        logger.debug(
            f"Channel {channel}: threshold={threshold_v}V, edge={edge}, "
            f"delay={delay_ps}ps, enabled={enabled}"
        )

    # ------------------------------------------------------------------
    # Histogram configuration
    # ------------------------------------------------------------------

    def configure_histogram(
        self,
        hist: int,
        *,
        stop_channel: int,
        ref_channel,
        bin_width_ps: Optional[int] = None,
        bin_count: int = 1024,
    ):
        """Configure a histogram block.

        Parameters
        ----------
        hist : int
            Histogram number (1–4).
        stop_channel : int
            Input channel (1–4) to use as the STOP signal.
        ref_channel : int or str
            Channel to use as the REF (START) signal. Pass an integer (1–4)
            or the string ``"start"`` for the START input.
        bin_width_ps : int or None
            Bin width in picoseconds. If ``None``, the device minimum
            resolution width is used automatically.
        bin_count : int
            Number of histogram bins (max 16384).
        """
        # TSCO5–8 forward DELA1–4 (one per input channel)
        stop_tsco = f"TSCO{stop_channel + 4}"
        ref_block = "STAR" if str(ref_channel).lower() == "start" else f"TSCO{ref_channel + 4}"

        if bin_width_ps is None:
            bin_width_ps = int(self._query("DEVI:RES:BWID?"))
        else:
            resolution = int(self._query("DEVI:RES:BWID?"))
            if bin_width_ps % resolution != 0:
                bin_width_ps = ((bin_width_ps // resolution) + 1) * resolution
                logger.warning(
                    f"bin_width_ps rounded up to {bin_width_ps} ps to align with device resolution"
                )

        self._cmd(f"HIST{hist}:STOP:LINK {stop_tsco}")
        self._cmd(f"HIST{hist}:REF:LINK {ref_block}")
        self._cmd(f"HIST{hist}:STOP:FILT RISI")
        self._cmd(f"HIST{hist}:REF:FILT RISI")
        self._cmd(f"HIST{hist}:ENAB:LINK REC")
        self._cmd(f"HIST{hist}:BWID {bin_width_ps}")
        self._cmd(f"HIST{hist}:BCOU {bin_count}")

        logger.debug(
            f"Histogram {hist}: stop=ch{stop_channel}, ref={ref_channel}, "
            f"bwid={bin_width_ps}ps, bins={bin_count}"
        )

    # ------------------------------------------------------------------
    # Count acquisition
    # ------------------------------------------------------------------

    def get_counts(self, channel: int, duration_s: float) -> int:
        """Read the total event count on one input channel over a time window.

        Configures the channel counter in accumulation mode, runs a single
        record of the requested duration, then reads and returns the count.

        Parameters
        ----------
        channel : int
            Input channel (1–4) or ``0`` for the START input.
        duration_s : float
            Integration window in seconds.

        Returns
        -------
        int
            Total number of events detected on the channel.
        """
        block = "STARt" if channel == 0 else f"INPU{channel}"
        duration_ps = int(duration_s * 1e12)

        self._cmd(f"{block}:COUN:MODE ACCU;RESEt")
        self._run_record(duration_ps)

        return int(self._query(f"{block}:COUNter?"))

    def get_count_rate(self, channel: int, integration_s: float = 0.1) -> float:
        """Return events per second on a channel.

        Parameters
        ----------
        channel : int
            Input channel (1–4) or ``0`` for the START input.
        integration_s : float
            Integration window in seconds (default 0.1 s).

        Returns
        -------
        float
            Count rate in counts per second.
        """
        counts = self.get_counts(channel, integration_s)
        return counts / integration_s

    # ------------------------------------------------------------------
    # Histogram acquisition
    # ------------------------------------------------------------------

    def get_histogram(
        self,
        hist: int,
        duration_s: float,
    ):
        """Acquire one histogram.

        The histogram must have been configured with :meth:`configure_histogram`
        before calling this method.

        Parameters
        ----------
        hist : int
            Histogram number to acquire (1–4).
        duration_s : float
            Acquisition duration in seconds.

        Returns
        -------
        x_ps : numpy.ndarray
            Bin centre times in picoseconds.
        y : numpy.ndarray
            Counts per bin.
        """
        duration_ps = int(duration_s * 1e12)
        bin_width_ps = int(self._query(f"HIST{hist}:BWID?"))
        bin_count = int(self._query(f"HIST{hist}:BCOU?"))

        self._cmd(f"HIST{hist}:FLUS")
        self._run_record(duration_ps)

        raw = self._query(f"HIST{hist}:DATA?")
        y = np.array(eval(raw), dtype=np.int64)

        x_ps = (np.arange(len(y)) + 0.5) * bin_width_ps
        return x_ps, y

    # ------------------------------------------------------------------
    # Timestamp streaming
    # ------------------------------------------------------------------

    def start_timestamp_stream(
        self,
        channels: Iterable[int],
        callback: Callable[[int, np.ndarray], None],
        output_dir: Optional[Path] = None,
    ):
        """Start streaming raw timestamps from one or more channels.

        Timestamps are delivered in chunks to ``callback`` as they arrive,
        making it possible to process them on the fly (e.g. autocorrelation)
        without writing large files.

        The Time Controller's RECord generator is left running in continuous
        mode (``REC:NUM 0``). Call :meth:`stop_timestamp_stream` to stop.

        Parameters
        ----------
        channels : iterable of int
            Channel numbers to stream (1–4).
        callback : callable
            Called as ``callback(channel, timestamps_ps)`` for each received
            chunk, where ``timestamps_ps`` is a ``numpy.ndarray`` of int64
            timestamps in picoseconds.
        output_dir : Path or None
            Directory passed to the DataLinkTargetService for its working
            files. Defaults to a ``dlt_tmp`` folder next to this module.
        """
        if output_dir is None:
            output_dir = Path(__file__).parent / "dlt_tmp"
        output_dir.mkdir(parents=True, exist_ok=True)

        self._dlt = _dlt_connect(output_dir, self.dlt_path)

        # Stop any acquisitions left open from a previous run
        active = _dlt_exec(self._dlt, "list") or []
        for acq_id in active:
            logger.warning(f"Closing leftover DLT acquisition '{acq_id}'")
            _dlt_exec(self._dlt, f"stop --id {acq_id}")

        channels = list(channels)

        # Configure record for continuous streaming
        self._cmd("REC:TRIG:ARM:MODE MANUal")
        self._cmd("REC:ENABle ON")
        self._cmd("REC:STOP")
        self._cmd("REC:NUM 0")  # infinite records

        for ch in channels:
            self._cmd(f"RAW{ch}:ERRORS:CLEAR")

            recv_port = _STREAM_BASE_PORT + ch
            client = _StreamClient(
                addr=f"tcp://localhost:{recv_port}",
                channel=ch,
                callback=callback,
            )
            client.start()
            self._stream_clients[ch] = client

            command = (
                f"start-stream --channel {ch} "
                f"--address {self.address} "
                f"--stream-port {recv_port}"
            )
            _dlt_exec(self._dlt, command)
            self._cmd(f"RAW{ch}:SEND ON")

        self._cmd("REC:PLAY")
        logger.info(f"Timestamp stream started on channels {channels}")

    def stop_timestamp_stream(self):
        """Stop an active timestamp stream and join the receiver threads."""
        if not self._stream_clients:
            return

        self._cmd("REC:STOP")

        for ch in list(self._stream_clients):
            try:
                self._cmd(f"RAW{ch}:SEND OFF")
            except Exception:
                pass

        # Tell the DLT to stop all active acquisitions so ports are freed
        if self._dlt is not None:
            try:
                active = _dlt_exec(self._dlt, "list") or []
                for acq_id in active:
                    _dlt_exec(self._dlt, f"stop --id {acq_id}")
            except Exception:
                pass

        for client in self._stream_clients.values():
            client.join()
        self._stream_clients.clear()

        logger.info("Timestamp stream stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cmd(self, command: str):
        """Send a SCPI command and discard the response."""
        self._tc.send_string(command)
        response = self._tc.recv().decode("utf-8")
        logger.debug(f"CMD  {command!r} -> {response!r}")

    def _query(self, command: str) -> str:
        """Send a SCPI query and return the response string."""
        self._tc.send_string(command)
        response = self._tc.recv().decode("utf-8")
        logger.debug(f"QURY {command!r} -> {response!r}")
        return response

    def _run_record(self, duration_ps: int):
        """Run a single timed acquisition and block until it finishes."""
        self._cmd("REC:TRIG:ARM:MODE MANUal")
        self._cmd("REC:ENABle ON")
        self._cmd("REC:STOP")
        self._cmd("REC:NUM 1")
        self._cmd(f"REC:DURation {duration_ps}")
        self._cmd("REC:PLAY")
        while self._query("REC:STAGe?").upper() == "PLAYING":
            time.sleep(0.05)


# ------------------------------------------------------------------
# Streaming helper thread
# ------------------------------------------------------------------

class _StreamClient(Thread):
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

    def run(self):
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

    def join(self, timeout=None):
        self._running = False
        super().join(timeout)


# ------------------------------------------------------------------
# Module-level utilities (mirror vendor common.py, no external dep)
# ------------------------------------------------------------------

def _check_host(address: str, port: int) -> bool:
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((address, port))
        return True
    except socket.error:
        return False
    finally:
        s.close()


def _dlt_connect(output_dir: Path, dlt_path: Path = DEFAULT_DLT_PATH) -> zmq.Socket:
    """Start the DataLinkTargetService if needed and return a ZMQ socket."""
    import json

    if dlt_path.is_dir():
        dlt_bin = dlt_path / "DataLinkTargetService.exe"
        dlt_dir = dlt_path
    else:
        dlt_bin = dlt_path
        dlt_dir = dlt_path.parent

    if not dlt_bin.exists():
        raise FileNotFoundError(f"DataLinkTargetService binary not found: {dlt_bin}")

    if not _check_host("localhost", DLT_PORT):
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
            )
        else:
            subprocess.Popen(
                [str(dlt_bin), "-f", str(output_dir)],
                stdout=subprocess.PIPE,
            )
        time.sleep(0.2)

    context = zmq.Context()
    sock = context.socket(zmq.REQ)
    sock.connect(f"tcp://localhost:{DLT_PORT}")
    return sock


def _dlt_exec(sock: zmq.Socket, command: str):
    import json

    sock.send_string(command)
    raw = sock.recv().decode("utf-8")
    answer = json.loads(raw) if raw.strip() else None

    if isinstance(answer, dict) and "error" in answer:
        msg = answer.get("error", {}).get("description", "unknown error")
        raise RuntimeError(f"DataLinkTarget error: {msg}")

    return answer
