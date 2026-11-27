"""Compatibility notice for the retired key-file generator."""
import sys


if __name__ == "__main__":
    sys.exit("Supply ZKAUTH_KEY from your secret manager or use an existing external "
             "mode-0600 ZKAUTH_KEY_FILE. See the Fedora setup in README.md.")
