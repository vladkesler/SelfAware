"""MockBoard: scripted order, regex claims, simulated liveness, the demo arc."""

from selfaware.hardware.mock_board import MockBoard, ScriptedExchange, demo_fail_then_pass_script


async def test_scripted_exchanges_consumed_in_order(mock_board: MockBoard) -> None:
    mock_board.queue(
        ScriptedExchange(stdout="first\n"),
        ScriptedExchange(stdout="second\n"),
    )
    r1 = await mock_board.exec("print('a')", timeout_s=1.0)
    r2 = await mock_board.exec("print('b')", timeout_s=1.0)
    assert r1.last_line == "first"
    assert r2.last_line == "second"
    assert mock_board.exec_log == ["print('a')", "print('b')"]


async def test_regex_exchange_only_claims_matching_exec(mock_board: MockBoard) -> None:
    mock_board.queue(ScriptedExchange(match=r"ADC\(27\)", stdout="scripted\n"))

    # non-matching exec falls through (script stays queued)
    miss = await mock_board.exec("print(1)", timeout_s=1.0)
    assert miss.stdout == ""

    hit = await mock_board.exec("from machine import ADC\nprint(ADC(27).read_u16())", timeout_s=1.0)
    assert hit.last_line == "scripted"


async def test_simulated_sensor_answers_and_stimulate_shifts_baseline(mock_board: MockBoard) -> None:
    code = "from machine import ADC\nprint(ADC(27).read_u16())"
    before = float((await mock_board.exec(code, timeout_s=1.0)).last_line)
    assert 25 < before < 85  # base 55 (unit '%'), sine amp 25 + noise

    mock_board.stimulate("ldr", 30)
    after = float((await mock_board.exec(code, timeout_s=1.0)).last_line)
    assert after - before > 15  # delta dominates sine+noise


async def test_ultrasonic_simulator_answers_in_cm_window(mock_board: MockBoard) -> None:
    code = "import machine\nprint(machine.time_pulse_us(machine.Pin(15), 1, 30000) / 58)"
    value = float((await mock_board.exec(code, timeout_s=1.0)).last_line)
    assert 2 < value < 400  # plausible HC-SR04 distance, never a negative timeout sentinel


async def test_output_harness_returns_the_print0_sentinel(mock_board: MockBoard) -> None:
    """servo/buzzer/fan: the host output payload soft-verifies via `print(0)`."""
    payload = (
        "class Driver:\n"
        "    def set(self, level):\n"
        "        pass\n"
        "_act = Driver()\n"
        "try:\n"
        "    _act.set(1)\n"
        "finally:\n"
        "    _act.set(0)\n"
        "print(0)\n"
    )
    result = await mock_board.exec(payload, timeout_s=1.0)
    assert result.ok
    assert result.last_line == "0"


async def test_demo_script_yields_verbatim_traceback_then_reading() -> None:
    board = MockBoard(script=demo_fail_then_pass_script())
    await board.connect()

    attempt1 = await board.exec("driver attempt 1", timeout_s=5.0)
    assert not attempt1.ok
    assert attempt1.stderr.startswith("Traceback (most recent call last):")
    assert 'File "<stdin>", line 11, in read' in attempt1.stderr
    assert "AttributeError: 'ADC' object has no attribute 'read'" in attempt1.stderr

    attempt2 = await board.exec("driver attempt 2", timeout_s=5.0)
    assert attempt2.ok
    value = float(attempt2.last_line)
    assert 2 < value < 100  # plausible AND not railed in the LDR '%' window — passes the analog judge


async def test_persistent_scan_responder_answers_every_scan_without_touching_the_script() -> None:
    """`.scan()` execs are answered from scan_addrs EVERY time, never from the
    script queue — so discovery cards appear before the commission and cannot
    vanish when the script runs out (the cards-vanishing-on-stage bug)."""
    board = MockBoard(script=[ScriptedExchange(stdout="beat\n")], scan_addrs=[0x3C, 0x70])
    scan_code = "from machine import I2C, Pin\nprint(I2C(0, sda=Pin(4), scl=Pin(5)).scan())\n"

    first = await board.exec(scan_code, timeout_s=1.0)
    second = await board.exec(scan_code, timeout_s=1.0)
    assert first.last_line == "[60, 112]"  # 0x3C OLED, 0x70 SHTC3
    assert second.last_line == "[60, 112]"  # persistent — never exhausted

    # the scripted beat is still intact: scans never consume the queue
    beat = await board.exec("Driver().read()", timeout_s=1.0)
    assert beat.last_line == "beat"


async def test_timeout_contract_flags_timed_out(mock_board: MockBoard) -> None:
    mock_board.queue(ScriptedExchange(stdout="too slow\n", delay_s=0.2))
    result = await mock_board.exec("anything", timeout_s=0.01)
    assert result.timed_out
    assert result.stdout == ""
