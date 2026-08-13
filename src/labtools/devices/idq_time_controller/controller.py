"""IDQuantique Time Controller SCPI wrapper.

Wraps the ZMQ SCPI interface into a class with methods for the three
acquisition modes used in this lab:

* **Counts** — read input event counts over an integration window
* **Histograms** — time-resolved photon arrival histograms (TCSPC)
* **Timestamps (streaming)** — on-the-fly delivery of raw timestamps via a
  callback, suitable for autocorrelation without accumulating large files

The class does not depend on the vendor example utilities directly; all SCPI
commands are issued through the private :meth:`_cmd` / :meth:`_query` helpers
so the communication layer is easy to swap later if needed. DataLinkTarget
process management and the streaming transport live in
:mod:`labtools.devices.idq_time_controller.dlt`.

Requirements
------------
* ``pyzmq`` must be installed in the environment.
* For timestamp streaming the DataLinkTargetService (DLT) executable must be
  reachable; its default path is ``dlt.DEFAULT_DLT_PATH``.

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

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

import numpy as np
import zmq

from labtools.devices.idq_time_controller import dlt

logger = logging.getLogger(__name__)


def _parse_numeric_response(raw: str, *, cast: type = float):
    """Convert SCPI responses like ``1000TB`` or ``0.1V`` into a numeric value."""
    text = str(raw).strip()
    if not text:
        raise ValueError("empty numeric response")

    match = re.match(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)
    if match is None:
        raise ValueError(f"could not parse numeric response from {raw!r}")
    return cast(match.group(0))


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

SCPI_PORT = 5555
_DEFAULT_DLT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "labtools_idq_dlt"

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
        dlt_path: Path = dlt.DEFAULT_DLT_PATH,
    ):
        self.address = address
        self.dlt_path = dlt_path

        self._context: Optional[zmq.Context] = None
        self._tc: Optional[zmq.Socket] = None          # SCPI socket
        self._dlt: Optional[zmq.Socket] = None         # DataLink socket
        self._dlt_process = None
        self._stream_clients: Dict[int, dlt.StreamClient] = {}
        self._stream_ports: Dict[int, int] = {}
        self._stream_ids: Dict[int, str] = {}

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the SCPI connection to the Time Controller."""
        if not dlt.check_host(self.address, SCPI_PORT):
            raise ConnectionError(
                f"Cannot reach Time Controller at {self.address}:{SCPI_PORT}. "
                "Check network and that the device is powered on."
            )
        self._context = zmq.Context()
        self._tc = self._context.socket(zmq.REQ)
        self._tc.setsockopt(zmq.RCVTIMEO, 2000)
        self._tc.setsockopt(zmq.SNDTIMEO, 2000)
        self._tc.connect(f"tcp://{self.address}:{SCPI_PORT}")
        logger.info(f"Connected to Time Controller at {self.address}")

    def disconnect(self) -> None:
        """Close all open connections and stop any active streams."""
        self.stop_timestamp_stream()
        if self._dlt is not None:
            try:
                self._dlt.close()
            except Exception:
                pass
            self._dlt = None
        if self._dlt_process is not None and self._dlt_process.poll() is None:
            try:
                self._dlt_process.terminate()
                self._dlt_process.wait(timeout=2.0)
            except Exception:
                try:
                    self._dlt_process.kill()
                except Exception:
                    pass
            finally:
                self._dlt_process = None
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

    def __enter__(self) -> IDQTimeController:
        self.connect()
        return self

    def __exit__(self, *_) -> None:
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
            bin_width_ps = _parse_numeric_response(self._query("DEVI:RES:BWID?"), cast=int)
        else:
            resolution = _parse_numeric_response(self._query("DEVI:RES:BWID?"), cast=int)
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

        return _parse_numeric_response(self._query(f"{block}:COUNter?"), cast=int)

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
        bin_width_ps = _parse_numeric_response(self._query(f"HIST{hist}:BWID?"), cast=int)
        bin_count = _parse_numeric_response(self._query(f"HIST{hist}:BCOU?"), cast=int)

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
            files. Defaults to a writable temp directory under the system temp
            folder, e.g. ``%TEMP%/labtools_idq_dlt``.
        """
        if output_dir is None:
            output_dir = _DEFAULT_DLT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        for attempt in range(2):
            try:
                self.ensure_dlt_running(output_dir)
                break
            except (ConnectionError, TimeoutError, RuntimeError):
                if attempt == 1:
                    raise
                logger.warning("DataLinkTarget did not respond; restarting it and retrying.")
                self._restart_dlt_service(output_dir)

        channels = list(channels)

        # Close any stale acquisitions from earlier failed runs so the service can
        # accept a clean stream start on the vendor's expected per-channel ports.
        self._close_active_dlt_streams()

        # Configure record for continuous streaming
        self._cmd("REC:TRIG:ARM:MODE MANUal")
        self._cmd("REC:ENABle ON")
        self._cmd("REC:STOP")
        self._cmd("REC:NUM 0")  # infinite records

        self._start_stream_channels(channels, callback)
        self._cmd("REC:PLAY")
        logger.info(f"Timestamp stream started on channels {channels}")

    def acquire_timestamp_stream(
        self,
        channels: Iterable[int],
        callback: Callable[[int, np.ndarray], None],
        duration_s: float,
        output_dir: Optional[Path] = None,
        timeout_s: float = 30.0,
    ) -> None:
        """Acquire a timed timestamp stream using the vendor lifecycle.

        This mirrors the vendor example flow: configure a single timed record,
        start the DLT streams, wait until the record and DLT transfer have
        completed, then cleanly stop the stream. This avoids truncating the
        acquisition mid-flush when the Python process stops the stream on a
        wall-time deadline.
        """
        if output_dir is None:
            output_dir = _DEFAULT_DLT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        for attempt in range(2):
            try:
                self.ensure_dlt_running(output_dir)
                break
            except (ConnectionError, TimeoutError, RuntimeError):
                if attempt == 1:
                    raise
                self._restart_dlt_service(output_dir)

        channels = list(channels)
        self._close_active_dlt_streams()

        self._cmd("REC:TRIG:ARM:MODE MANUal")
        self._cmd("REC:ENABle ON")
        self._cmd("REC:STOP")
        self._cmd("REC:NUM 1")
        self._cmd(f"REC:DURation {int(duration_s * 1e12)}")

        self._start_stream_channels(channels, callback)
        self._cmd("REC:PLAY")

        try:
            self.wait_for_timestamp_stream_idle(timeout_s=timeout_s)
        finally:
            self.stop_timestamp_stream()

        logger.info(f"Timed timestamp stream completed for channels {channels} (duration={duration_s:.3f}s)")

    def wait_for_timestamp_stream_idle(self, timeout_s: float = 30.0):
        """Wait until the acquisition has finished and the DLT is quiescent."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            stage = ""
            try:
                stage = self._query("REC:STAGe?").upper()
            except Exception:
                stage = ""

            status_ok = False
            for channel, stream_id in list(self._stream_ids.items()):
                if self._dlt is None:
                    continue
                try:
                    info = dlt.dlt_exec(self._dlt, f"status --id {stream_id}")
                except Exception:
                    info = {}
                if not isinstance(info, dict):
                    continue
                if info.get("error"):
                    raise RuntimeError(f"timestamp stream error on channel {channel}: {info.get('error')}")
                inactivity = float(info.get("inactivity", 0.0) or 0.0)
                acquisitions = int(info.get("acquisitions_count", 0) or 0)
                if acquisitions > 0 and inactivity >= 1.0:
                    status_ok = True
                    break

            if stage != "PLAYING" and status_ok:
                return
            time.sleep(0.05)

        raise TimeoutError(
            f"Timed out waiting for timestamp stream completion after {timeout_s}s"
        )

    def stop_timestamp_stream(self):
        """Stop an active timestamp stream and join the receiver threads."""
        if not self._stream_clients:
            return

        try:
            self._cmd("REC:STOP")
        except TimeoutError:
            logger.warning("REC:STOP timed out; continuing stream shutdown")

        for ch in list(self._stream_clients):
            try:
                self._cmd(f"RAW{ch}:SEND OFF")
            except TimeoutError:
                logger.warning(f"RAW{ch}:SEND OFF timed out; ignoring")
            except Exception:
                pass

            stream_id = self._stream_ids.get(ch)
            if stream_id is not None and self._dlt is not None:
                try:
                    dlt.dlt_exec(self._dlt, f"stop --id {stream_id}")
                except Exception:
                    logger.warning(f"Could not stop DLT stream {stream_id} for channel {ch}")

        for client in self._stream_clients.values():
            client.join(timeout=2.0)
        self._stream_clients.clear()
        self._stream_ports.clear()
        self._stream_ids.clear()

        logger.info("Timestamp stream stopped")

    def _start_stream_channels(
        self,
        channels: Iterable[int],
        callback: Callable[[int, np.ndarray], None],
    ):
        """Start a stream client and register the DLT acquisition for each channel."""
        for ch in channels:
            self._cmd(f"RAW{ch}:ERRORS:CLEAR")

            recv_port = _STREAM_BASE_PORT + ch
            self._stream_ports[ch] = recv_port
            client = dlt.StreamClient(
                addr=f"tcp://localhost:{recv_port}",
                channel=ch,
                callback=callback,
            )
            client.start()
            self._stream_clients[ch] = client
            time.sleep(0.05)

            command = (
                f"start-stream --channel {ch} "
                f"--address {self.address} "
                f"--stream-port {recv_port}"
            )
            answer = dlt.dlt_exec(self._dlt, command)
            self._stream_ids[ch] = answer["id"]

            deadline = time.time() + 3.0
            while time.time() < deadline:
                try:
                    active = dlt.dlt_exec(self._dlt, "list") or []
                except Exception:
                    active = []
                if self._stream_ids[ch] in active:
                    break
                time.sleep(0.05)

            time.sleep(0.05)
            self._cmd(f"RAW{ch}:SEND ON")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cmd(self, command: str):
        """Send a SCPI command and discard the response."""
        try:
            self._tc.send_string(command)
            response = self._tc.recv().decode("utf-8")
        except zmq.Again as exc:
            raise TimeoutError(f"SCPI command timed out: {command}") from exc
        logger.debug(f"CMD  {command!r} -> {response!r}")

    def _query(self, command: str) -> str:
        """Send a SCPI query and return the response string."""
        try:
            self._tc.send_string(command)
            response = self._tc.recv().decode("utf-8")
        except zmq.Again as exc:
            raise TimeoutError(f"SCPI query timed out: {command}") from exc
        logger.debug(f"QURY {command!r} -> {response!r}")
        return response

    def _close_active_dlt_streams(self):
        """Stop any DLT acquisitions still running from previous attempts."""
        if self._dlt is None:
            return
        try:
            active = dlt.dlt_exec(self._dlt, "list") or []
        except Exception:
            return

        for acquisition_id in active:
            try:
                dlt.dlt_exec(self._dlt, f"stop --id {acquisition_id}")
            except Exception:
                pass

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

    def _is_dlt_healthy(self, output_dir: Path) -> bool:
        """Return True if the DLT service is reachable and can answer a list command."""
        if not dlt.check_host("localhost", dlt.DLT_PORT):
            return False
        try:
            if self._dlt is None:
                self._dlt = dlt.dlt_connect(output_dir, self.dlt_path)
            dlt.dlt_exec(self._dlt, "list")
            return True
        except Exception:
            return False

    def _launch_dlt_service(self, output_dir: Path):
        """Start the vendor DLT service in a writable working directory."""
        dlt_bin = self.dlt_path if self.dlt_path.is_file() else self.dlt_path / "DataLinkTargetService.exe"
        if not dlt_bin.exists():
            raise FileNotFoundError(f"DataLinkTargetService binary not found: {dlt_bin}")

        dlt_root = self.dlt_path if self.dlt_path.is_dir() else self.dlt_path.parent
        config_template = dlt_root / "config" / "DataLinkTargetService.log.conf"
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
            self._dlt_process = subprocess.Popen(
                [str(dlt_bin), "-f", str(output_dir), "--logconf", str(log_conf)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(output_dir),
            )
        else:
            self._dlt_process = subprocess.Popen(
                [str(dlt_bin), "-f", str(output_dir)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(output_dir),
            )

    def _restart_dlt_service(self, output_dir: Path):
        """Force the DLT service to restart if it has died or stopped responding."""
        if self._dlt is not None:
            try:
                self._dlt.close()
            except Exception:
                pass
            self._dlt = None
        if self._dlt_process is not None and self._dlt_process.poll() is None:
            try:
                self._dlt_process.terminate()
                self._dlt_process.wait(timeout=2.0)
            except Exception:
                try:
                    self._dlt_process.kill()
                except Exception:
                    pass
        self._dlt_process = None
        self._launch_dlt_service(output_dir)

    def ensure_dlt_running(self, output_dir: Optional[Path] = None):
        """Ensure the DataLinkTargetService is running and responsive.

        This is useful before starting any streaming or file-based timestamp
        acquisition. If the service is dead or the local port does not answer,
        the helper restarts it.
        """
        if output_dir is None:
            output_dir = _DEFAULT_DLT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        if self._is_dlt_healthy(output_dir):
            return

        self._restart_dlt_service(output_dir)
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if self._is_dlt_healthy(output_dir):
                return
            time.sleep(0.2)

        raise ConnectionError(
            "DataLinkTargetService did not respond after restart; "
            f"checked {self.dlt_path}."
        )
