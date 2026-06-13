import os
import sys
import pytest

if __name__ == "__main__":
    print("Triggering Automated Tests...")
    # Isolate tests to separate JSON files using prefix
    os.environ["TICKETING_DB_PREFIX"] = "test_db_"
    
    # Run pytest and return the exit code
    exit_code = pytest.main(["tests/", "-v"])
    sys.exit(exit_code)
