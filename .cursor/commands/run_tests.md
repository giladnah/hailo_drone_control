/run_tests = Use the run_terminal_cmd tool to execute "./scripts/px4ctl.sh test" to run all tests against the simulator.

## Context
This command runs the pytest test suite including:
- Environment tests (verify Docker setup)
- Integration tests (MAVLink connectivity, telemetry)
- Functional tests (takeoff, landing, missions)

The simulator must be running first. Use `/start_simulator` if needed.

For specific tests, you can run:
- `./scripts/px4ctl.sh test tests/test_integration.py` - Integration tests only
- `./scripts/px4ctl.sh test tests/test_functional.py` - Functional tests only

