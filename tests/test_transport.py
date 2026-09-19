"""Exercise host protocol handling using an external serial byte-stream double."""

import unittest

from arm_control.transport import LinkError, SerialLink


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class SerialStream:
    def __init__(self, clock, responses=None, boot=b"ROBOT_ARM 2 90 90 90 90\n"):
        self.clock = clock
        self.responses = responses or {}
        self.incoming = bytearray(boot)
        self.writes = []
        self.closed = False
        self.timeout = 0.5
        self.write_timeout = 0.5
        self.write_error = None
        self.read_error = None
        self.short_write = False

    @property
    def in_waiting(self):
        return len(self.incoming)

    def reset_input_buffer(self):
        self.incoming.clear()

    def write(self, data):
        if self.closed or self.write_error:
            raise self.write_error or OSError("disconnected")
        self.writes.append(data)
        self.incoming.extend(self.responses.get(data, b""))
        return len(data) - int(self.short_write)

    def read(self, size=1):
        if self.closed or self.read_error:
            raise self.read_error or OSError("disconnected")
        if not self.incoming:
            self.clock.sleep(self.timeout)
            return b""
        # Deliberately return single-byte fragments regardless of requested size.
        data = bytes(self.incoming[:1])
        del self.incoming[:1]
        return data

    def close(self):
        self.closed = True


class PersistentDeviceStream(SerialStream):
    """Device RX state survives host close/open; opening does not reset it."""

    def __init__(self, clock):
        super().__init__(clock)
        self.device_line = bytearray()
        self.next_write_limit = None
        self.resumed_at = None
        self.accepted_resumes = []
        self.applied_poses = []
        self.applied_manual = []
        self.completed_lines = []

    def write(self, data):
        if self.closed:
            raise OSError("disconnected")
        self.writes.append(data)
        count = len(data) if self.next_write_limit is None else self.next_write_limit
        self.next_write_limit = None
        for byte in data[:count]:
            if byte != 10:
                self.device_line.append(byte)
                continue
            command = bytes(self.device_line)
            self.device_line.clear()
            self.completed_lines.append((command, self.clock()))
            if not command:
                continue
            if b"\x00" in command:
                reply = b"ERR invalid\n"
            elif command == b"hello":
                self.resumed_at = None
                reply = b"ROBOT_ARM 2 70 80 90 100\n"
            elif command == b"resume":
                self.resumed_at = self.clock()
                self.accepted_resumes.append(self.clock())
                reply = b"OK resume\n"
            elif command == b"all 180":
                self.applied_manual.append(command)
                reply = b"OK\n"
            elif command == b"pose 10 20 30 40":
                if self.resumed_at is not None:
                    self.applied_poses.append(command)
                    reply = b"OK pose\n"
                else:
                    reply = b"ERR paused\n"
            else:
                reply = b"ERR syntax\n"
            self.incoming.extend(reply)
        return count


class TransportTests(unittest.TestCase):
    def make_link(self, responses=None, timeout=0.5):
        clock = Clock()
        serial = SerialStream(clock, responses if responses is not None else {
            b"hello\n": b"ROBOT_ARM 2 70 80 90 100\r\n",
            b"resume\n": b"OK resume\n",
            b"hold\n": b"OK hold 71 81 91 101\n",
            b"off\n": b"OK off\n",
            b"pose 10 20 30 40\n": b"OK pose\n",
        })
        opened = []

        def factory(**kwargs):
            opened.append(kwargs)
            return serial

        link = SerialLink("FAKE", timeout=timeout, serial_factory=factory,
                          clock=clock, sleep=clock.sleep)
        return link, serial, clock, opened

    def test_construction_does_not_open_and_handshake_uses_fresh_held_angles(self):
        link, serial, clock, opened = self.make_link()
        self.assertEqual(opened, [])
        self.assertEqual(link.connect(), (70.0, 80.0, 90.0, 100.0))
        self.assertEqual(serial.writes, [b"\x00\n", b"hello\n"])
        self.assertGreaterEqual(clock.now, 2.0)
        self.assertEqual(opened[0]["baudrate"], 115200)
        self.assertGreater(opened[0]["timeout"], 0)
        self.assertLessEqual(opened[0]["write_timeout"], 0.5)

    def test_resume_pose_hold_roundtrip_with_partial_crlf_responses(self):
        link, serial, _, _ = self.make_link()
        link.connect()
        link.resume()
        link.send_pose((10.1, 19.9, 30, 40))
        self.assertEqual(link.hold(), (71.0, 81.0, 91.0, 101.0))
        self.assertEqual(serial.writes,
                         [b"\x00\n", b"hello\n", b"resume\n", b"pose 10 20 30 40\n", b"hold\n"])

    def test_close_sends_hold_then_releases_port(self):
        link, serial, _, _ = self.make_link()
        link.connect()
        link.resume()
        link.close()
        self.assertEqual(serial.writes[-1], b"hold\n")
        self.assertTrue(serial.closed)
        link.close()

    def test_off_then_resume_allows_poses_again(self):
        link, serial, _, _ = self.make_link()
        link.connect()
        link.resume()
        link.send_pose((10, 20, 30, 40))
        link.off()
        self.assertFalse(serial.closed)
        link.resume()
        link.send_pose((10, 20, 30, 40))
        self.assertEqual(serial.writes[-4:],
                         [b"pose 10 20 30 40\n", b"off\n", b"resume\n", b"pose 10 20 30 40\n"])

    def test_off_requires_another_explicit_resume_before_pose(self):
        link, serial, _, _ = self.make_link()
        link.connect()
        link.resume()
        link.off()
        with self.assertRaisesRegex(LinkError, "resume explicitly"):
            link.send_pose((10, 20, 30, 40))
        self.assertEqual(serial.writes[-1], b"off\n")
        self.assertNotIn(b"pose 10 20 30 40\n", serial.writes)

    def test_off_requires_exact_ack_and_disconnects_on_failure(self):
        for reply in (b"OK hold\n", b"OK off extra\n", b"ERR unavailable\n",
                      b"OK of", b"", b"OK off\nOK off\n"):
            with self.subTest(reply=reply):
                link, serial, clock, _ = self.make_link()
                link.connect()
                link.resume()
                serial.responses[b"off\n"] = reply
                start = clock.now
                with self.assertRaises(LinkError):
                    link.off()
                self.assertTrue(serial.closed)
                self.assertLessEqual(clock.now - start, 0.5)
                with self.assertRaises(LinkError):
                    link.resume()

    def test_off_disconnect_is_wrapped_and_port_is_closed(self):
        link, serial, _, _ = self.make_link()
        link.connect()
        link.resume()
        serial.write_error = OSError("unplugged")
        with self.assertRaisesRegex(LinkError, "unplugged"):
            link.off()
        self.assertTrue(serial.closed)

    def test_boot_identification_without_hello_response_times_out(self):
        link, serial, clock, _ = self.make_link({})
        with self.assertRaises(LinkError):
            link.connect()
        self.assertTrue(serial.closed)
        self.assertLessEqual(clock.now, 3.0)

    def test_bad_handshakes_close_the_link(self):
        for reply in (b"ROBOT_ARM 3 90 90 90 90\n", b"ROBOT_ARM 2 90 90 90\n",
                      b"ROBOT_ARM 2 -2147483649 90 90 90\n", b"ROBOT_ARM 2 90 2147483648 90 90\n",
                      b"ROBOT_ARM 2 90.0 90 90 90\n", b"ROBOT_ARM 2 True 90 90 90\n",
                      b"ROBOT_ARM 2 --1 90 90 90\n", b"OK resume\n", b"\xff\n",
                      b"X" * 96 + b"\n", b"ROBOT_ARM 2 90 90 90 90\nOK pose\n"):
            with self.subTest(reply=reply):
                link, serial, _, _ = self.make_link({b"hello\n": reply})
                with self.assertRaises(LinkError):
                    link.connect()
                self.assertTrue(serial.closed)

    def test_pose_requires_explicit_resume(self):
        link, serial, _, _ = self.make_link()
        link.connect()
        with self.assertRaises(LinkError):
            link.send_pose((10, 20, 30, 40))
        self.assertNotIn(b"pose 10 20 30 40\n", serial.writes)

    def test_invalid_angles_never_reach_wire(self):
        for angles in ((1, 2, 3), (1, 2, 3, 4, 5), (-2147483649, 2, 3, 4),
                       (2147483648, 2, 3, 4), (float("nan"), 2, 3, 4),
                       (float("inf"), 2, 3, 4), (True, 2, 3, 4), ("90", 2, 3, 4),
                       (-float("inf"), 2, 3, 4), (10 ** 1000, 2, 3, 4)):
            with self.subTest(angles=angles):
                link, serial, _, _ = self.make_link()
                link.connect()
                link.resume()
                with self.assertRaises(LinkError):
                    link.send_pose(angles)
                self.assertEqual(serial.writes, [b"\x00\n", b"hello\n", b"resume\n"])

    def test_pose_requires_exact_ack_and_disconnects_on_firmware_error(self):
        for reply in (b"OK resume\n", b"OK pose extra\n", b"ERR timeout\n",
                      b"ERR paused\n", b"OK po", b"", b"OK pose\nOK pose\n"):
            with self.subTest(reply=reply):
                link, serial, clock, opened = self.make_link()
                link.connect()
                link.resume()
                serial.responses[b"pose 10 20 30 40\n"] = reply
                start = clock.now
                with self.assertRaises(LinkError):
                    link.send_pose((10, 20, 30, 40))
                self.assertLessEqual(clock.now - start, 0.5)
                self.assertTrue(serial.closed)
                with self.assertRaises(LinkError):
                    link.resume()
                self.assertEqual(len(opened), 1)

    def test_stale_ack_or_firmware_error_is_not_accepted_as_next_reply(self):
        for stale in (b"OK pose\n", b"ERR timeout\n"):
            with self.subTest(stale=stale):
                link, serial, _, _ = self.make_link()
                link.connect()
                link.resume()
                serial.incoming.extend(stale)
                with self.assertRaises(LinkError):
                    link.send_pose((10, 20, 30, 40))
                self.assertEqual(serial.writes, [b"\x00\n", b"hello\n", b"resume\n"])
                self.assertTrue(serial.closed)

    def test_read_write_disconnection_and_short_write_close_link(self):
        for failure in ("read_error", "write_error", "short_write"):
            with self.subTest(failure=failure):
                link, serial, _, _ = self.make_link()
                link.connect()
                setattr(serial, failure, True if failure == "short_write" else OSError("unplugged"))
                with self.assertRaises(LinkError):
                    link.resume()
                self.assertTrue(serial.closed)

    def test_close_is_bounded_even_if_hold_is_unanswered(self):
        link, serial, clock, _ = self.make_link()
        link.connect()
        serial.responses[b"hold\n"] = b""
        start = clock.now
        link.close()
        self.assertLessEqual(clock.now - start, 0.5)
        self.assertTrue(serial.closed)

    def test_reconnect_handshakes_and_does_not_resume(self):
        link, serial, _, opened = self.make_link()
        link.connect()
        link.resume()
        link.close()
        serial.closed = False
        self.assertEqual(link.connect(), (70, 80, 90, 100))
        self.assertEqual(len(opened), 2)
        self.assertEqual(serial.writes[-1], b"hello\n")
        with self.assertRaises(LinkError):
            link.send_pose((10, 20, 30, 40))

    def test_invalid_timeout_is_rejected_before_open(self):
        for timeout in (0, -1, 0.6, float("inf"), float("nan"), 10 ** 1000):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    self.make_link(timeout=timeout)

    def test_write_and_read_share_one_timeout_budget(self):
        link, serial, clock, _ = self.make_link()
        link.connect()
        write = serial.write

        def slow_write(data):
            clock.sleep(0.3)
            return write(data)

        serial.write = slow_write
        serial.responses[b"resume\n"] = b"OK res"
        start = clock.now
        with self.assertRaises(LinkError):
            link.resume()
        self.assertLessEqual(clock.now - start, 0.5)
        self.assertTrue(serial.closed)

    def test_concurrent_request_is_rejected_without_queuing_another_command(self):
        link, serial, _, _ = self.make_link()
        link.connect()
        write = serial.write

        def interrupted_write(data):
            with self.assertRaisesRegex(LinkError, "in progress"):
                link.hold()
            return write(data)

        serial.write = interrupted_write
        link.resume()
        self.assertEqual(serial.writes, [b"\x00\n", b"hello\n", b"resume\n"])
        self.assertFalse(serial.closed)

    def test_failed_port_open_is_wrapped_and_never_retried_implicitly(self):
        opened = []

        def unavailable(**kwargs):
            opened.append(kwargs)
            raise OSError("port busy")

        link = SerialLink("FAKE", serial_factory=unavailable)
        with self.assertRaisesRegex(LinkError, "port busy"):
            link.connect()
        with self.assertRaises(LinkError):
            link.resume()
        link.close()
        self.assertEqual(len(opened), 1)

    def test_reconnect_recovers_persistent_partial_device_line_without_applying_pose(self):
        for fragment in (b"pose 10 20", b"pose 10 20 30 40"):
            with self.subTest(fragment=fragment):
                clock = Clock()
                serial = PersistentDeviceStream(clock)

                def reopen(**kwargs):
                    serial.closed = False
                    return serial

                link = SerialLink("FAKE", serial_factory=reopen, clock=clock, sleep=clock.sleep)
                link.connect()
                link.resume()
                serial.next_write_limit = len(fragment)
                with self.assertRaisesRegex(LinkError, "Incomplete serial write"):
                    link.send_pose((10, 20, 30, 40))
                self.assertEqual(serial.device_line, fragment)
                reconnect_at = clock()
                self.assertEqual(link.connect(), (70, 80, 90, 100))
                self.assertEqual(serial.writes[-2:], [b"\x00\n", b"hello\n"])
                self.assertEqual(serial.device_line, b"")
                self.assertEqual(serial.applied_poses, [])
                completed_at = [when for command, when in serial.completed_lines if command == fragment + b"\x00"]
                self.assertGreaterEqual(completed_at[-1] - reconnect_at, 2.0)
                self.assertLessEqual(clock() - reconnect_at, 3.0)

    def test_resync_discards_its_error_but_does_not_accept_error_as_hello(self):
        link, serial, _, _ = self.make_link({b"\x00\n": b"ERR invalid\n", b"hello\n": b"ERR unavailable\n"})
        with self.assertRaisesRegex(LinkError, "unavailable"):
            link.connect()
        self.assertTrue(serial.closed)

    def test_resync_invalidates_pending_manual_and_resume_commands_without_executing(self):
        for pending in (b"all 180", b"resume", b"pose 10 20 30 40", b"pose 10 20"):
            with self.subTest(pending=pending):
                clock = Clock()
                serial = PersistentDeviceStream(clock)
                serial.device_line.extend(pending)
                link = SerialLink("FAKE", serial_factory=lambda **kwargs: serial,
                                  clock=clock, sleep=clock.sleep)
                self.assertEqual(link.connect(), (70, 80, 90, 100))
                self.assertEqual(serial.accepted_resumes, [])
                self.assertEqual(serial.applied_manual, [])
                self.assertEqual(serial.applied_poses, [])
                self.assertEqual(serial.device_line, b"")
                self.assertEqual(serial.writes, [b"\x00\n", b"hello\n"])

    def test_unterminated_resync_reply_is_drained_with_a_finite_budget(self):
        link, serial, clock, _ = self.make_link({
            b"\x00\n": b"ERR unfinished", b"hello\n": b"ROBOT_ARM 2 70 80 90 100\n",
        })
        self.assertEqual(link.connect(), (70, 80, 90, 100))
        self.assertEqual(serial.writes, [b"\x00\n", b"hello\n"])
        self.assertLessEqual(clock(), 3.0)

    def test_partial_invalid_frame_write_does_not_proceed_to_hello(self):
        link, serial, _, _ = self.make_link()
        serial.short_write = True
        with self.assertRaisesRegex(LinkError, "Incomplete serial framing reset"):
            link.connect()
        self.assertEqual(serial.writes, [b"\x00\n"])
        self.assertTrue(serial.closed)

    def test_protocol_two_accepts_signed_hello_and_hold_through_int32_boundaries(self):
        link, serial, _, _ = self.make_link({
            b"hello\n": b"ROBOT_ARM 2 -2147483648 -270 450 2147483647\r\n",
            b"hold\n": b"OK hold -2147483648 -1 181 2147483647\n",
        })
        self.assertEqual(link.connect(), (-2147483648, -270, 450, 2147483647))
        self.assertEqual(link.hold(), (-2147483648, -1, 181, 2147483647))

    def test_pose_rounds_signed_angles_without_old_travel_limits(self):
        for angles, command in (
            ((-270.2, 450.4, -90.8, 181.2), b"pose -270 450 -91 181\n"),
            ((-2147483648, 2147483647, -1, 0), b"pose -2147483648 2147483647 -1 0\n"),
            ((-2147483648.4, 2147483647.4, -0.1, 180.9), b"pose -2147483648 2147483647 0 181\n"),
        ):
            with self.subTest(angles=angles):
                link, serial, _, _ = self.make_link()
                serial.responses[command] = b"OK pose\n"
                link.connect()
                link.resume()
                link.send_pose(angles)
                self.assertEqual(serial.writes[-1], command)

    def test_protocol_one_is_rejected_with_clear_incompatibility_error(self):
        link, serial, _, _ = self.make_link({b"hello\n": b"ROBOT_ARM 1 90 90 90 90\n"})
        with self.assertRaisesRegex(LinkError, "requires protocol 2.*reported 1"):
            link.connect()
        self.assertTrue(serial.closed)

    def test_hold_rejects_malformed_or_non_int32_values(self):
        for reply in (b"OK hold -2147483649 0 0 0\n", b"OK hold 2147483648 0 0 0\n",
                      b"OK hold True 0 0 0\n", b"OK hold -1.5 0 0 0\n",
                      b"OK hold 1e2 0 0 0\n", b"OK hold - 0 0 0\n"):
            with self.subTest(reply=reply):
                link, serial, _, _ = self.make_link()
                link.connect()
                serial.responses[b"hold\n"] = reply
                with self.assertRaises(LinkError):
                    link.hold()
                self.assertTrue(serial.closed)


if __name__ == "__main__":
    unittest.main()
