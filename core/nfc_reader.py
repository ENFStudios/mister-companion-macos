import time
from dataclasses import dataclass

try:
    import serial
    from serial.tools import list_ports
except Exception:
    serial = None
    list_ports = None


class NFCReaderError(RuntimeError):
    pass


@dataclass
class SerialReaderInfo:
    port: str
    description: str


@dataclass
class NFCTokenReadResult:
    port: str
    uid: str
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
INDATA_RETRIES = 2
POLL_FOR_TAG_TIMEOUT = 0.2


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
            raise NFCReaderError("No NDEF text record was found on the token.")

        if index >= len(memory):
            raise NFCReaderError("Invalid NDEF data on the token.")

        length = memory[index]
        index += 1

        if length == 0xFF:
            if index + 2 > len(memory):
                raise NFCReaderError("Invalid extended NDEF length on the token.")
            length = int.from_bytes(memory[index:index + 2], "big")
            index += 2

        ndef = memory[index:index + length]
        if len(ndef) != length:
            raise NFCReaderError("Incomplete NDEF data on the token.")

        if len(ndef) < 5:
            raise NFCReaderError("NDEF record is too small.")

        flags = ndef[0]
        type_length = ndef[1]

        if not flags & 0x10:
            raise NFCReaderError("Only short NDEF records are supported.")

        payload_length = ndef[2]
        type_start = 3
        payload_start = type_start + type_length

        record_type = ndef[type_start:payload_start]
        payload = ndef[payload_start:payload_start + payload_length]

        if record_type != b"T":
            raise NFCReaderError("The token does not contain an NDEF text record.")

        if not payload:
            return ""

        language_length = payload[0] & 0x3F
        text_bytes = payload[1 + language_length:]

        return text_bytes.decode("utf-8", errors="replace")

    raise NFCReaderError("No NDEF text record was found on the token.")


class PN532ReaderSerial:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.7):
        if serial is None:
            raise NFCReaderError("pyserial is not installed.")

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
            raise NFCReaderError("PN532 is not open.")

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

        raise NFCReaderError("Timed out waiting for PN532 response.")

    def _send_command(self, command: int, params: bytes = b"", timeout: float = FAST_COMMAND_TIMEOUT) -> bytes:
        if self.device is None:
            raise NFCReaderError("PN532 is not open.")

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
            raise NFCReaderError(
                f"PN532 acknowledged {command_name}, but no valid response was received.\n\n"
                f"Last detail: {last_error or 'No response frame received.'}"
            )

        raise NFCReaderError(
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
            raise NFCReaderError("Could not read PN532 firmware version.")
        return response

    def poll_for_tag(self) -> bytes | None:
        try:
            response = self._send_command(0x4A, b"\x01\x00", timeout=POLL_FOR_TAG_TIMEOUT)
        except Exception:
            return None

        if not response or response[0] < 1:
            return None

        if len(response) < 7:
            return None

        uid_length = response[5]
        uid = response[6:6 + uid_length]

        if not uid:
            return None

        return uid

    def in_data_exchange(self, payload: bytes, timeout: float = FAST_EXCHANGE_TIMEOUT) -> bytes:
        command_label = payload.hex(" ").upper()
        last_error = ""

        for attempt in range(INDATA_RETRIES):
            try:
                response = self._send_command(0x40, b"\x01" + payload, timeout=timeout)

                if not response:
                    raise NFCReaderError(
                        f"Empty PN532 data exchange response for payload: {command_label}"
                    )

                status = response[0]
                if status != 0x00:
                    raise NFCReaderError(
                        f"PN532 data exchange failed for payload {command_label}: 0x{status:02X}"
                    )

                return response[1:]

            except Exception as e:
                last_error = str(e)

                if attempt == 0:
                    try:
                        self._send_command(0x4A, b"\x01\x00", timeout=1.0)
                    except Exception:
                        pass

                time.sleep(0.08)

        raise NFCReaderError(
            f"PN532 InDataExchange failed for payload: {command_label}\n\n"
            f"Last detail: {last_error}"
        )

    def ntag_read_page(self, page: int) -> bytes:
        return self.in_data_exchange(bytes([0x30, page & 0xFF]), timeout=FAST_EXCHANGE_TIMEOUT)

    def read_ndef_text_payload(self, max_pages: int = 64) -> str:
        memory = bytearray()
        page = 4
        pages_read = 0

        while pages_read < max_pages:
            chunk = self.ntag_read_page(page)
            memory.extend(chunk[:16])

            pages_read += 4
            page += 4

            if 0xFE in chunk:
                break

        return _decode_ndef_text_from_memory(bytes(memory))


def _open_working_reader(port: str) -> PN532ReaderSerial:
    errors = []

    for baudrate in BAUDRATES_TO_TRY:
        reader = None

        try:
            reader = PN532ReaderSerial(port, baudrate=baudrate)
            reader.open()
            reader.initialize()
            return reader
        except Exception as e:
            errors.append(f"{baudrate}: {e}")
            try:
                if reader is not None:
                    reader.close()
            except Exception:
                pass

    joined_errors = "\n".join(errors)
    raise NFCReaderError(
        f"Could not communicate with PN532 on {port}.\n\n"
        f"Tried baudrates: {', '.join(str(x) for x in BAUDRATES_TO_TRY)}\n\n"
        f"Details:\n{joined_errors}\n\n"
        f"Make sure no other app is using the serial port."
    )


def open_reader(port: str | None = None) -> PN532ReaderSerial:
    if port:
        return _open_working_reader(port)

    readers = list_serial_readers()
    errors = []

    for item in readers:
        try:
            return _open_working_reader(item.port)
        except Exception as e:
            errors.append(f"{item.port}: {e}")

    if errors:
        raise NFCReaderError(
            "No working PN532 reader was found.\n\n"
            + "\n\n".join(errors)
        )

    raise NFCReaderError("No serial ports were found. Connect your PN532 USB reader and try again.")


def read_token_once(port: str | None = None) -> NFCTokenReadResult | None:
    reader = open_reader(port)

    try:
        uid = reader.poll_for_tag()
        if not uid:
            return None

        payload = reader.read_ndef_text_payload()

        return NFCTokenReadResult(
            port=f"{reader.port} @ {reader.baudrate}",
            uid=_to_hex(uid),
            payload=payload,
        )
    finally:
        reader.close()


def read_token_from_open_reader(reader: PN532ReaderSerial) -> NFCTokenReadResult | None:
    uid = reader.poll_for_tag()
    if not uid:
        return None

    payload = reader.read_ndef_text_payload()

    return NFCTokenReadResult(
        port=f"{reader.port} @ {reader.baudrate}",
        uid=_to_hex(uid),
        payload=payload,
    )