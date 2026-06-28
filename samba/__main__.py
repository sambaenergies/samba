# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
from samba._version import __version__


def main() -> None:
    print(f"samba {__version__}")


if __name__ == "__main__":
    main()
