"""Run once to generate SHAD_MASTER_PASSWORD_HASH for the .env file.
Usage: python gen_password_hash.py 'your chosen password'
"""
import sys
from auth import hash_password

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python gen_password_hash.py 'your chosen password'")
        raise SystemExit(1)
    print(hash_password(sys.argv[1]))
