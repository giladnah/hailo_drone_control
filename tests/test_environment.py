"""
Environment verification tests for the PX4 development container.

These tests verify that all required tools and dependencies
are properly installed in the Docker container.
"""

import subprocess
import sys


def test_arm_gcc_installed():
    """
    Test that ARM GCC cross-compiler is available.

    Returns:
        bool: True if ARM GCC is found and working.
    """
    result = subprocess.run(
        ["arm-none-eabi-gcc", "--version"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, "ARM GCC not found"
    assert "arm-none-eabi-gcc" in result.stdout
    print(f"✓ ARM GCC: {result.stdout.split(chr(10))[0]}")
    return True


def test_mavlink_router_installed():
    """
    Test that MAVLink-Router is available.

    Returns:
        bool: True if mavlink-routerd is found.
    """
    result = subprocess.run(
        ["which", "mavlink-routerd"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, "mavlink-routerd not found"
    print(f"✓ MAVLink-Router: {result.stdout.strip()}")
    return True


def test_mavsdk_installed():
    """
    Test that MAVSDK Python package is available.

    Returns:
        bool: True if MAVSDK can be imported.
    """
    try:
        import mavsdk
        # MAVSDK may not have __version__, check if System class exists
        from mavsdk import System
        print("✓ MAVSDK Python: installed (System class available)")
        return True
    except ImportError as e:
        raise AssertionError(f"MAVSDK not installed: {e}")


def test_px4_python_deps():
    """
    Test that PX4 Python dependencies are available.

    Returns:
        bool: True if all critical packages are importable.
    """
    # Map pip package names to import names
    required_packages = [
        ("em", "empy", "3.3.4"),  # import name, pip name, expected version
        ("jinja2", "jinja2", None),
        ("serial", "pyserial", None),
        ("yaml", "pyyaml", None),
        ("numpy", "numpy", None),
    ]

    for import_name, pip_name, expected_version in required_packages:
        try:
            mod = __import__(import_name)
            version = getattr(mod, "__version__", getattr(mod, "VERSION", "unknown"))
            if expected_version and str(version) != expected_version:
                print(f"⚠ {pip_name}: {version} (expected {expected_version})")
            else:
                print(f"✓ {pip_name}: {version}")
        except ImportError:
            raise AssertionError(f"Package {pip_name} not installed (import {import_name})")

    return True


def test_gazebo_available():
    """
    Test that Gazebo Garden is available.

    Returns:
        bool: True if gz command is found.
    """
    result = subprocess.run(
        ["which", "gz"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("⚠ Gazebo (gz) not found in PATH - may need setup")
        return False

    # Get version
    version_result = subprocess.run(
        ["gz", "--version"],
        capture_output=True,
        text=True
    )
    if version_result.returncode == 0:
        print(f"✓ Gazebo: {version_result.stdout.strip()}")
    else:
        print(f"✓ Gazebo: found at {result.stdout.strip()}")
    return True


def test_px4_binary():
    """
    Test that PX4 SITL binary exists and is executable.

    Returns:
        bool: True if PX4 binary is found and executable.
    """
    import os

    px4_binary = "/workspace/PX4-Autopilot/build/px4_sitl_default/bin/px4"

    if not os.path.exists(px4_binary):
        print(f"⚠ PX4 binary not found at {px4_binary}")
        print("  Run 'make px4_sitl_default' to build")
        return False

    if not os.access(px4_binary, os.X_OK):
        raise AssertionError(f"PX4 binary not executable: {px4_binary}")

    print(f"✓ PX4 SITL binary: {px4_binary}")
    return True


def run_all_tests():
    """
    Run all environment tests.

    Returns:
        int: Number of failed tests.
    """
    tests = [
        ("ARM GCC", test_arm_gcc_installed),
        ("MAVLink-Router", test_mavlink_router_installed),
        ("MAVSDK", test_mavsdk_installed),
        ("PX4 Python Deps", test_px4_python_deps),
        ("Gazebo", test_gazebo_available),
        ("PX4 Binary", test_px4_binary),
    ]

    print("=" * 50)
    print("PX4 Development Environment Tests")
    print("=" * 50)
    print()

    passed = 0
    failed = 0
    warnings = 0

    for name, test_func in tests:
        print(f"Testing {name}...")
        try:
            result = test_func()
            if result:
                passed += 1
            else:
                warnings += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
        print()

    print("=" * 50)
    print(f"Results: {passed} passed, {warnings} warnings, {failed} failed")
    print("=" * 50)

    return failed


if __name__ == "__main__":
    sys.exit(run_all_tests())

