import time
from dataclasses import dataclass

try:
    import serial
    from serial.tools import list_ports
except Exception:
    serial = None
    list_ports = None


class NFCWriterError(RuntimeError):
    pass


@dataclass
class SerialReaderInfo:
    port: str
    description: str


@dataclass
class NFCTagInfo:
    uid: str
    tag_type: str
    usable_bytes: int


@dataclass
class NFCWriteResult:
    port: str
    uid: str
    tag_type: str
    payload: str


ACK_FRAME = b"\x00\x00\xff\x00\xff\x00"

BAUDRATES_TO_TRY = [
    115200,
    9600,
    57600,
    38400,
    19200,
]

FAST_COMMAND_TIMEOUT = 1.2
FAST_EXCHANGE_TIMEOUT = 1.5
SAFE_EXCHANGE_TIMEOUT = 3.0
INDATA_RETRIES = 2

NTAG_STORAGE_MAP = {
    0x0F: ("NTAG213", 144),
    0x11: ("NTAG215", 504),
    0x13: ("NTAG216", 888),
}


def list_serial_readers() -> list[SerialReaderInfo]:
    if list_ports is None:
        return []

    readers = []
    for item in list_ports.comports():
        readers.append(
            SerialReaderInfo(
                port=item.device,
                description=item.description or item.device,
            )
        )

    return readers


def _checksum(values: bytes) -> int:
    return (-sum(values)) & 0xFF


def _to_hex(data: bytes) -> str:
    return "".join(f"{value:02X}" for value in data)


def _build_ndef_text_payload(text: str) -> bytes:
    text_bytes = text.encode("utf-8")
    language = b"en"
    record_payload = bytes([len(language)]) + language + text_bytes

    if len(record_payload) > 255:
        raise NFCWriterError("Payload is too large for a short NDEF text record.")

    ndef_record = bytes(
        [
            0xD1,
            0x01,
            len(record_payload),
            0x54,
        ]
    ) + record_payload

    if len(ndef_record) < 255:
        tlv = bytes([0x03, len(ndef_record)]) + ndef_record + bytes([0xFE])
    else:
        tlv = (
            bytes([0x03, 0xFF])
            + len(ndef_record).to_bytes(2, "big")
            + ndef_record
            + bytes([0xFE])
        )

    while len(tlv) % 4:
        tlv += b"\x00"

    return tlv


def _decode_ndef_text_from_memory(memory: bytes) -> str:
    index = 0

    while index < len(memory):
        tag = memory[index]
        index += 1

        if tag == 0x00:
            continue

        if tag == 0xFE:
            break

        if tag != 0x03:
            raise NFCWriterError("No NDEF text record was found on the token.")

        if index >= len(memory):
            raise NFCWriterError("Invalid NDEF data on the token.")

        length = memory[index]
        index += 1

        if length == 0xFF:
            if index + 2 > len(memory):
                raise NFCWriterError("Invalid extended NDEF length on the token.")
            length = int.from_bytes(memory[index:index + 2], "big")
            index += 2

        ndef = memory[index:index + length]
        if len(ndef) != length:
            raise NFCWriterError("Incomplete NDEF data on the token.")

        if len(ndef) < 5:
            raise NFCWriterError("NDEF record is too small.")

        flags = ndef[0]
        type_length = ndef[1]

        if not flags & 0x10:
            raise NFCWriterError("Only short NDEF records are supported.")

        payload_length = ndef[2]
        type_start = 3
        payload_start = type_start + type_length

        record_type = ndef[type_start:payload_start]
        payload = ndef[payload_start:payload_start + payload_length]

        if record_type != b"T":
            raise NFCWriterError("The token does not contain an NDEF text record.")

        if not payload:
            return ""

        language_length = payload[0] & 0x3F
        text_bytes = payload[1 + language_length:]

        return text_bytes.decode("utf-8", errors="replace")

    raise NFCWriterError("No NDEF text record was found on the token.")


class PN532Serial:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.7):
        if serial is None:
            raise NFCWriterError("pyserial is not installed.")

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.device = None

    def open(self):
        self.device = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=2,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

        try:
            self.device.setDTR(False)
            self.device.setRTS(False)
        except Exception:
            pass

        time.sleep(0.2)

        try:
            self.device.reset_input_buffer()
            self.device.reset_output_buffer()
        except Exception:
            pass

        self._wake_up()

    def close(self):
        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _wake_up(self):
        if self.device is None:
            return

        wake_sequences = [
            b"\x55" * 16 + b"\x00" * 16 + b"\xff" * 4 + b"\x00" * 4,
            b"\x55\x55\x00\x00\x00\x00",
            b"\x00\x00\xff\x00\xff\x00",
            b"\x55" * 32 + b"\x00" * 8,
        ]

        for seq in wake_sequences:
            try:
                self.device.write(seq)
                self.device.flush()
                time.sleep(0.15)
            except Exception:
                pass

        try:
            self.device.reset_input_buffer()
        except Exception:
            pass

    def _read_frame(self, timeout: float = 2.0) -> bytes:
        if self.device is None:
            raise NFCWriterError("PN532 is not open.")

        deadline = time.time() + timeout
        buffer = b""

        while time.time() < deadline:
            chunk = self.device.read(1)
            if not chunk:
                continue

            buffer += chunk

            if len(buffer) > 12:
                buffer = buffer[-12:]

            if buffer.endswith(b"\x00\x00\xff"):
                length_raw = self.device.read(2)
                if len(length_raw) != 2:
                    continue

                length = length_raw[0]
                length_checksum = length_raw[1]

                if length == 0x00 and length_checksum == 0xFF:
                    self.device.read(1)
                    return ACK_FRAME

                if ((length + length_checksum) & 0xFF) != 0:
                    continue

                data = self.device.read(length)
                checksum = self.device.read(1)
                self.device.read(1)

                if len(data) != length or len(checksum) != 1:
                    continue

                if ((sum(data) + checksum[0]) & 0xFF) != 0:
                    continue

                return data

        raise NFCWriterError("Timed out waiting for PN532 response.")

    def _send_command(self, command: int, params: bytes = b"", timeout: float = FAST_COMMAND_TIMEOUT) -> bytes:
        if self.device is None:
            raise NFCWriterError("PN532 is not open.")

        command_names = {
            0x02: "GetFirmwareVersion",
            0x14: "SAMConfiguration",
            0x4A: "InListPassiveTarget",
            0x40: "InDataExchange",
        }

        command_name = command_names.get(command, f"Command 0x{command:02X}")

        data = bytes([0xD4, command]) + params
        length = len(data)

        frame = (
            b"\x00\x00\xff"
            + bytes([length, (-length) & 0xFF])
            + data
            + bytes([_checksum(data), 0x00])
        )

        try:
            self.device.reset_input_buffer()
        except Exception:
            pass

        self.device.write(frame)
        self.device.flush()

        expected_response_code = (command + 1) & 0xFF
        deadline = time.time() + timeout
        saw_ack = False
        last_error = ""

        while time.time() < deadline:
            remaining = max(0.2, deadline - time.time())

            try:
                response = self._read_frame(timeout=remaining)
            except Exception as e:
                last_error = str(e)
                break

            if response == ACK_FRAME:
                saw_ack = True
                continue

            if len(response) < 2:
                last_error = f"Short PN532 frame: {response.hex(' ').upper()}"
                continue

            if response[0] != 0xD5:
                last_error = f"Unexpected PN532 frame: {response.hex(' ').upper()}"
                continue

            if response[1] != expected_response_code:
                last_error = (
                    f"Unexpected PN532 response code: "
                    f"expected 0x{expected_response_code:02X}, "
                    f"got 0x{response[1]:02X}. "
                    f"Frame: {response.hex(' ').upper()}"
                )
                continue

            return response[2:]

        if saw_ack:
            raise NFCWriterError(
                f"PN532 acknowledged {command_name}, but no valid response was received.\n\n"
                f"Last detail: {last_error or 'No response frame received.'}"
            )

        raise NFCWriterError(
            f"PN532 did not return a valid response for {command_name}.\n\n"
            f"Last detail: {last_error or 'No response received.'}"
        )

    def initialize(self):
        self.get_firmware_version()

        try:
            self._send_command(0x14, b"\x01\x14\x01", timeout=3.0)
        except Exception:
            try:
                self._send_command(0x14, b"\x01\x01\x00", timeout=3.0)
            except Exception:
                pass

    def get_firmware_version(self) -> bytes:
        response = self._send_command(0x02, timeout=FAST_COMMAND_TIMEOUT)
        if len(response) < 4:
            raise NFCWriterError("Could not read PN532 firmware version.")
        return response

    def wait_for_tag(self, timeout: float = 10.0) -> bytes:
        deadline = time.time() + timeout
        last_error = ""

        while time.time() < deadline:
            try:
                response = self._send_command(0x4A, b"\x01\x00", timeout=2.0)
            except Exception as e:
                last_error = str(e)
                time.sleep(0.15)
                continue

            if not response or response[0] < 1:
                time.sleep(0.15)
                continue

            if len(response) < 7:
                last_error = f"Short tag response: {response.hex(' ').upper()}"
                time.sleep(0.15)
                continue

            uid_length = response[5]
            uid = response[6:6 + uid_length]

            if uid:
                return uid

            time.sleep(0.15)

        if last_error:
            raise NFCWriterError(f"No NFC token was detected.\n\nLast detail: {last_error}")

        raise NFCWriterError("No NFC token was detected.")

    def in_data_exchange(self, payload: bytes, timeout: float = FAST_EXCHANGE_TIMEOUT) -> bytes:
        command_label = payload.hex(" ").upper()
        last_error = ""

        for attempt in range(INDATA_RETRIES):
            try:
                response = self._send_command(0x40, b"\x01" + payload, timeout=timeout)

                if not response:
                    raise NFCWriterError(
                        f"Empty PN532 data exchange response for payload: {command_label}"
                    )

                status = response[0]
                if status != 0x00:
                    raise NFCWriterError(
                        f"PN532 data exchange failed for payload {command_label}: 0x{status:02X}"
                    )

                return response[1:]

            except Exception as e:
                last_error = str(e)

                if attempt == 0:
                    try:
                        self._send_command(0x4A, b"\x01\x00", timeout=2.0)
                    except Exception:
                        pass

                time.sleep(0.08)

        raise NFCWriterError(
            f"PN532 InDataExchange failed for payload: {command_label}\n\n"
            f"Last detail: {last_error}"
        )

    def ntag_get_version(self) -> bytes:
        try:
            return self.in_data_exchange(b"\x60", timeout=FAST_EXCHANGE_TIMEOUT)
        except Exception:
            return b""

    def ntag_read_page(self, page: int) -> bytes:
        return self.in_data_exchange(bytes([0x30, page & 0xFF]), timeout=FAST_EXCHANGE_TIMEOUT)

    def ntag_write_page(self, page: int, data: bytes):
        if len(data) != 4:
            raise ValueError("NTAG pages must be written in 4-byte chunks.")

        self.in_data_exchange(
            bytes([0xA2, page & 0xFF]) + data,
            timeout=FAST_EXCHANGE_TIMEOUT,
        )


def _open_working_reader(port: str) -> PN532Serial:
    errors = []

    for baudrate in BAUDRATES_TO_TRY:
        pn532 = None

        try:
            pn532 = PN532Serial(port, baudrate=baudrate)
            pn532.open()
            pn532.initialize()
            return pn532
        except Exception as e:
            errors.append(f"{baudrate}: {e}")
            try:
                if pn532 is not None:
                    pn532.close()
            except Exception:
                pass

    joined_errors = "\n".join(errors)
    raise NFCWriterError(
        f"Could not communicate with PN532 on {port}.\n\n"
        f"Tried baudrates: {', '.join(str(x) for x in BAUDRATES_TO_TRY)}\n\n"
        f"Details:\n{joined_errors}\n\n"
        f"Make sure no other app is using the COM port."
    )


def _detect_ntag_type(pn532: PN532Serial) -> tuple[str, int]:
    try:
        page_3_to_6 = pn532.ntag_read_page(3)
        if len(page_3_to_6) >= 4:
            cc = page_3_to_6[:4]

            if cc[0] == 0xE1 and cc[1] in (0x10, 0x12):
                size = cc[2] * 8

                if size <= 144:
                    return "NTAG213", 144

                if size <= 504:
                    return "NTAG215", 504

                if size <= 888:
                    return "NTAG216", 888
    except Exception:
        pass

    version = pn532.ntag_get_version()

    if len(version) >= 7:
        storage_size = version[6]
        if storage_size in NTAG_STORAGE_MAP:
            return NTAG_STORAGE_MAP[storage_size]

    raise NFCWriterError(
        "Unsupported NFC token. MiSTer Companion currently supports NTAG213, NTAG215, and NTAG216."
    )


def _write_ndef_text(pn532: PN532Serial, payload: str, usable_bytes: int) -> int:
    data = _build_ndef_text_payload(payload)

    if len(data) > usable_bytes:
        raise NFCWriterError(
            f"The selected path is too large for this token.\n\n"
            f"Required: {len(data)} bytes\n"
            f"Available: {usable_bytes} bytes"
        )

    if usable_bytes == 144:
        cc_size = 0x12
    elif usable_bytes == 504:
        cc_size = 0x3F
    elif usable_bytes == 888:
        cc_size = 0x6F
    else:
        cc_size = usable_bytes // 8

    pn532.ntag_write_page(3, bytes([0xE1, 0x10, cc_size & 0xFF, 0x00]))

    start_page = 4
    for offset in range(0, len(data), 4):
        page = start_page + (offset // 4)
        pn532.ntag_write_page(page, data[offset:offset + 4])

    return len(data)


def _read_ndef_text(pn532: PN532Serial, usable_bytes: int, expected_length: int | None = None) -> str:
    memory = bytearray()
    start_page = 4

    if expected_length is not None:
        pages_to_read = max(1, (expected_length + 3) // 4)
    else:
        pages_to_read = usable_bytes // 4

    page = start_page
    pages_read = 0

    while pages_read < pages_to_read:
        chunk = pn532.ntag_read_page(page)
        memory.extend(chunk[:16])

        pages_read += 4
        page += 4

        if 0xFE in chunk:
            break

    return _decode_ndef_text_from_memory(bytes(memory))


def test_reader(port: str) -> bool:
    try:
        pn532 = _open_working_reader(port)
        pn532.close()
        return True
    except Exception:
        return False


def auto_detect_reader() -> PN532Serial:
    readers = list_serial_readers()
    errors = []

    for reader in readers:
        try:
            return _open_working_reader(reader.port)
        except Exception as e:
            errors.append(f"{reader.port}: {e}")

    if errors:
        raise NFCWriterError(
            "No working PN532 reader was found.\n\n"
            + "\n\n".join(errors)
        )

    raise NFCWriterError("No serial ports were found. Connect your PN532 USB reader and try again.")


def read_tag_info(port: str | None = None, timeout: float = 15.0) -> NFCTagInfo:
    pn532 = _open_working_reader(port) if port else auto_detect_reader()

    try:
        uid = pn532.wait_for_tag(timeout=timeout)
        tag_type, usable_bytes = _detect_ntag_type(pn532)

        return NFCTagInfo(
            uid=_to_hex(uid),
            tag_type=tag_type,
            usable_bytes=usable_bytes,
        )
    finally:
        pn532.close()


def write_payload_to_token(payload: str, port: str | None = None, timeout: float = 15.0) -> NFCWriteResult:
    payload = (payload or "").strip()

    if not payload:
        raise NFCWriterError("No payload was provided.")

    pn532 = _open_working_reader(port) if port else auto_detect_reader()

    try:
        uid = pn532.wait_for_tag(timeout=timeout)
        tag_type, usable_bytes = _detect_ntag_type(pn532)

        written_length = _write_ndef_text(pn532, payload, usable_bytes)

        verified_payload = _read_ndef_text(
            pn532,
            usable_bytes,
            expected_length=written_length,
        )

        if verified_payload != payload:
            raise NFCWriterError(
                "The token was written, but verification failed.\n\n"
                f"Expected:\n{payload}\n\n"
                f"Read back:\n{verified_payload}"
            )

        return NFCWriteResult(
            port=f"{pn532.port} @ {pn532.baudrate}",
            uid=_to_hex(uid),
            tag_type=tag_type,
            payload=verified_payload,
        )
    finally:
        pn532.close()